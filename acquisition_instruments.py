import serial # permite comunicación serial
import time # para manejo de tiempos
import csv # para manejo de archivos CSV
import os # para verificar existencia de archivos
import threading # Permite ejecutar la adquisición en un hilo separado para no bloquear la interfaz gráfica
import tkinter as tk # Permite crear la ventana gráfica y los botones de control
import logging
import ast # para evaluación segura de expresiones literales
from contextlib import contextmanager
from typing import List, Dict, Optional, Any
import pyvisa
from datetime import datetime

# Configurar logging para adquisición
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('./logs/acquisition.log')
    ]
)
logger = logging.getLogger(__name__)

# Configuración de CSV y puertos
csv_file = f"Datos_{time.strftime('%Y%m%d_%H%M%S')}.csv" # Archivo CSV para guardar datos (valor por defecto)
# Parámetros de ciclo de histéresis
num_ciclos = 1
punto_inicio = 0
punto_final = 6.867
setpoint_intervalo = 60 # Intervalo en segundos para cambiar el setpoint
num_puntos_intermedios = 2
stability_time = 15  # Tiempo de estabilización en segundos después de cambiar el setpoint

# Modo de puntos intermedios
intermediate_mode = "automatic"  # "automatic" o "manual"
custom_points_text = "[0, 1, 2, 3, 4, 5, 6, 6.5, 6.8]"  # Puntos personalizados para modo manual

# Configuración de puertos seriales
alicat_port = "COM5"
tiva_port = "COM6"

# Configuración Keithley (simplificada para integración)
keithley_config = {
    'experiment_label': 'integrated_acquisition',
    'samples_per_count': 1,  # Una lectura por iteración para sincronizar
    'nplc_cycles': 1,
    'infinite_mode': False,
    'num_blocks': 1,  # No usado en este contexto
    'no_stats': True,
    'output_dir': '.',  # Directorio actual
    'quiet': True
}

# Variables de control globales
acquisition_running = False  # Bandera para saber si la adquisición está activa
acquisition_paused = False   # Bandera para saber si la adquisición está pausada
thread_acquisition = None # Variable donde se guarda el hilo de adquisición para poder detenerlo/join

# Variables globales para conexiones
ser_tiva_global = None
ser_alicat_global = None
keithley_acquirer_global = None

class KeithleyAcquisition:
    """Clase principal para adquisición de datos Keithley"""

    def __init__(self, config: Dict[str, Any], logger: Optional[logging.Logger] = None):
        self.config = config
        self.logger = logger or logging.getLogger(__name__)

        # Estado interno
        self.rm = None
        self.inst = None
        self.stop_acquisition = False
        self.interruption_thread = None
        self.csv_writer = None
        self.csv_file = None

        # Dependencias opcionales
        self._check_dependencies()

    def _check_dependencies(self):
        """Verifica las dependencias opcionales disponibles"""
        try:
            import numpy as np
            self.numpy_available = True
        except ImportError:
            self.numpy_available = False
            self.logger.warning("NumPy no disponible - algunas funciones limitadas")

        try:
            import keyboard
            self.keyboard_available = True
        except ImportError:
            self.keyboard_available = False
            self.logger.warning("Keyboard no disponible - interrupción manual no disponible")

    @contextmanager
    def instrument_connection(self):
        """Context manager para manejar la conexión del instrumento"""
        try:
            self._connect_instrument()
            yield self.inst
        finally:
            self._disconnect_instrument()

    def _connect_instrument(self):
        """Establece conexión con el instrumento Keithley"""
        try:
            # Intentar NI-VISA primero
            self.rm = pyvisa.ResourceManager('@ni')
            self.logger.info("Using NI-VISA backend")
        except Exception as e:
            self.logger.warning(f"NI-VISA not available, using default backend: {e}")
            self.rm = pyvisa.ResourceManager()

        # Listar recursos disponibles
        available_resources = list(self.rm.list_resources())
        self.logger.info(f"Available resources: {available_resources}")

        if not available_resources:
            raise KeithleyConnectionError("No se encontraron instrumentos conectados")

        # Usar el primer recurso disponible (puede mejorarse para selección específica)
        resource_name = available_resources[0]
        self.logger.info(f"Using resource: {resource_name}")

        try:
            self.inst = self.rm.open_resource(resource_name)
            self.logger.info("Instrument connection opened")

            # Configurar timeout dinámico
            timeout = self._calculate_timeout()
            self.inst.timeout = timeout
            self.logger.info(f"Timeout set to {timeout}ms")

            # Inicializar instrumento
            self._initialize_instrument()

        except Exception as e:
            raise KeithleyConnectionError(f"Error conectando al instrumento: {e}")

    def _calculate_timeout(self) -> int:
        """Calcula el timeout apropiado basado en la configuración"""
        base_timeout = 30000  # 30 segundos base
        nplc_factor = float(self.config['nplc_cycles']) if isinstance(self.config['nplc_cycles'], (int, float)) else 10
        estimated_time = self.config['samples_per_count'] * nplc_factor * 0.0001
        dynamic_timeout = max(30000, int(base_timeout + estimated_time * 1000))
        return dynamic_timeout

    def _initialize_instrument(self):
        """Inicializa el instrumento con la configuración apropiada"""
        # Modo remoto
        self.inst.write(':SYSTem:REMote')
        time.sleep(0.5)

        # Reset
        self.inst.write('*RST')
        time.sleep(1)

        # Limpiar estado
        self.inst.write('*CLS')

        # Configurar medición de voltaje DC
        self.inst.write('CONFigure:VOLTage:DC')

        # Auto-ranging
        self.inst.write('VOLTage:DC:RANGe:AUTO ON')

        # NPLCycles
        self.inst.write(f'SENSe:VOLTage:DC:NPLCycles {self.config["nplc_cycles"]}')

        # Verificar configuración
        # cast to float for comparison
        current_nplc = float(self.inst.query('SENSe:VOLTage:DC:NPLCycles?').strip())
        if current_nplc != float(self.config['nplc_cycles']):
            self.logger.warning(f"NPLCycles verification failed: expected {self.config['nplc_cycles']}, got {current_nplc}")

        self.logger.info("Instrument initialized successfully")

    def _disconnect_instrument(self):
        """Cierra la conexión con el instrumento"""
        try:
            if self.inst:
                self.inst.close()
                self.logger.info("Instrument connection closed")
            if self.rm:
                self.rm.close()
                self.logger.info("Resource manager closed")
        except Exception as e:
            self.logger.error(f"Error closing instrument connection: {e}")

    def setup_csv_output(self) -> str:
        """Configura el archivo CSV para salida de datos"""
        import os

        # Asegurar que el directorio de salida existe
        output_dir = self.config['output_dir']
        if not os.path.exists(output_dir):
            os.makedirs(output_dir, exist_ok=True)
            self.logger.info(f"Created output directory: {output_dir}")

        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f'dc_voltage_readings_{self.config["experiment_label"]}_{timestamp}.csv'
        filepath = os.path.join(output_dir, filename)

        self.csv_file = open(filepath, 'w', newline='')
        self.csv_writer = csv.writer(self.csv_file)
        self.csv_writer.writerow(['Block', 'Sample_In_Block', 'Global_Sample', 'Voltage_V', 'Timestamp'])

        self.logger.info(f"CSV file initialized: {filepath}")
        return filepath

    def start_interruption_monitor(self):
        """Inicia el monitoreo de interrupción por teclado"""
        if not self.keyboard_available:
            self.logger.warning("Keyboard interruption not available")
            return

        self.stop_acquisition = False
        self.interruption_thread = threading.Thread(
            target=self._monitor_interruption,
            daemon=True
        )
        self.interruption_thread.start()
        self.logger.info("Interruption monitor started")

    def _monitor_interruption(self):
        """Monitorea interrupción por teclado en un thread separado"""
        import keyboard

        print("\n🔴 Presiona 'q' o 'ESC' para detener la adquisición...")
        self.logger.info("Interruption listener started - press 'q' or 'ESC' to stop")

        while not self.stop_acquisition:
            try:
                if keyboard.is_pressed('q') or keyboard.is_pressed('esc'):
                    self.stop_acquisition = True
                    print("\n🛑 Interrupción detectada! Deteniendo adquisición...")
                    self.logger.warning("Acquisition interrupted by user")
                    break
                time.sleep(0.1)
            except Exception as e:
                self.logger.error(f"Error in interruption monitor: {e}")
                break

    def stop_interruption_monitor(self):
        """Detiene el monitoreo de interrupción"""
        if self.interruption_thread and self.interruption_thread.is_alive():
            self.stop_acquisition = True
            self.interruption_thread.join(timeout=1.0)
            self.logger.info("Interruption monitor stopped")

    def acquire_block(self, block_num: int) -> List[float]:
        """
        Adquiere un bloque de datos

        Args:
            block_num: Número del bloque actual

        Returns:
            Lista de voltajes adquiridos
        """
        if not self.inst:
            raise KeithleyAcquisitionError("Instrument not connected")

        # Verificar interrupción
        if self.stop_acquisition:
            return []

        # Configurar número de muestras
        self.inst.write(f'SAMPle:COUNt {self.config["samples_per_count"]}')
        self.logger.debug(f"Sample count set to {self.config['samples_per_count']} for block {block_num}")

        # Iniciar medición
        self.inst.write('INITiate:IMMediate')
        self.logger.debug(f"Initiated measurement for block {block_num}")

        # Esperar completación
        self._wait_for_completion(block_num)

        # Obtener lecturas
        readings_str = self.inst.query('FETCh?')
        block_readings = [float(r) for r in readings_str.strip().split(',')]

        if len(block_readings) != self.config['samples_per_count']:
            self.logger.warning(f"Expected {self.config['samples_per_count']} readings, got {len(block_readings)}")

        # self.logger.info(f"Block {block_num} completed: {len(block_readings)} samples")
        return block_readings

    def _wait_for_completion(self, block_num: int):
        """Espera a que se complete la medición del bloque"""
        poll_start = time.time()
        poll_count = 0

        while True:
            poll_count += 1
            try:
                opc_response = self.inst.query('*OPC?').strip()
                if opc_response == '1':
                    break
            except Exception as e:
                self.logger.error(f"Error polling completion for block {block_num}: {e}")
                raise KeithleyAcquisitionError(f"Polling error for block {block_num}: {e}")

            elapsed = time.time() - poll_start
            if elapsed > 30:  # Timeout after 30 seconds
                raise KeithleyAcquisitionError(f"Timeout waiting for block {block_num} completion")

            time.sleep(0.1)

        block_time = time.time() - poll_start
        # self.logger.info(f"Block {block_num} completed in {block_time:.3f}s after {poll_count} polls")

    def save_block_data(self, block_readings: List[float], block_num: int,
                       global_sample_index: int) -> int:
        """
        Guarda los datos del bloque en CSV

        Args:
            block_readings: Lecturas del bloque
            block_num: Número del bloque
            global_sample_index: Índice global actual

        Returns:
            Nuevo índice global después de guardar
        """
        if not self.csv_writer:
            raise KeithleyAcquisitionError("CSV output not initialized")

        block_timestamp = datetime.now().isoformat()

        for i, voltage in enumerate(block_readings, 1):
            self.csv_writer.writerow([
                block_num, i, global_sample_index + i, voltage, block_timestamp
            ])

        return global_sample_index + len(block_readings)

    def run_acquisition(self) -> Dict[str, Any]:
        """
        Ejecuta la adquisición completa de datos

        Returns:
            Diccionario con resultados de la adquisición
        """
        results = {
            'total_samples': 0,
            'blocks_completed': 0,
            'total_time': 0,
            'csv_file': None,
            'interrupted': False,
            'error': None
        }

        try:
            with self.instrument_connection() as inst:
                # Configurar salida CSV
                csv_file = self.setup_csv_output()
                results['csv_file'] = csv_file

                # Iniciar monitoreo de interrupción
                self.start_interruption_monitor()

                # Mostrar información de la adquisición
                self._print_acquisition_info()

                # Confirmar inicio
                if not self._confirm_start():
                    results['error'] = "Acquisition cancelled by user"
                    return results

                # Bucle principal de adquisición
                start_time = time.time()
                global_sample_index = 0
                block_num = 0

                while self._should_continue_acquisition(block_num):
                    block_num += 1

                    if self.stop_acquisition:
                        self._handle_interruption(block_num, results)
                        break

                    # Adquirir bloque
                    block_start_time = time.time()
                    block_readings = self.acquire_block(block_num)

                    if not block_readings:
                        break

                    # Guardar datos
                    global_sample_index = self.save_block_data(
                        block_readings, block_num, global_sample_index
                    )

                    # Reportar progreso
                    self._report_block_progress(block_num, block_readings, block_start_time)

                # Calcular resultados finales
                total_time = time.time() - start_time
                results.update({
                    'total_samples': global_sample_index,
                    'blocks_completed': block_num,
                    'total_time': total_time,
                    'interrupted': self.stop_acquisition
                })

                self._print_final_results(results)

        except Exception as e:
            results['error'] = str(e)
            self.logger.error(f"Acquisition error: {e}")
        finally:
            # Limpiar recursos
            self.stop_interruption_monitor()
            if self.csv_file:
                self.csv_file.close()

        return results

    def _should_continue_acquisition(self, block_num: int) -> bool:
        """Determina si debe continuar la adquisición"""
        if self.config['infinite_mode']:
            return not self.stop_acquisition
        else:
            return block_num < self.config['num_blocks'] and not self.stop_acquisition

    def _print_acquisition_info(self):
        """Imprime información sobre la adquisición"""
        if self.config['infinite_mode']:
            print(f"\n=== Iniciando adquisición infinita ===")
            print("📊 Modo indefinido: continuará hasta interrupción manual")
        else:
            total_expected = self.config['num_blocks'] * self.config['samples_per_count']
            nplc_factor = float(self.config['nplc_cycles']) if isinstance(self.config['nplc_cycles'], (int, float)) else 10
            estimated_time = self.config['num_blocks'] * self.config['samples_per_count'] * nplc_factor * 0.0001
            print(f"\n=== Iniciando adquisición de {self.config['num_blocks']} bloques ===")
            print(f"📊 Total esperado: {total_expected:,} muestras")
            print(f"⏱️ Tiempo estimado: {estimated_time:.1f} segundos ({estimated_time/60:.1f} minutos)")

    def _confirm_start(self) -> bool:
        """Confirma el inicio de la adquisición"""
        if self.config.get('quiet', False):
            return True

        confirm = input("¿Desea continuar? (y/n): ").strip().lower()
        return confirm in ['y', 'yes', 's', 'si', '']

    def _handle_interruption(self, block_num: int, results: Dict):
        """Maneja la interrupción de la adquisición"""
        if self.config['infinite_mode']:
            print(f"\n🛑 Adquisición interrumpida en el bloque {block_num} (modo indefinido)")
        else:
            progress_percent = ((block_num - 1) / self.config['num_blocks']) * 100
            print(f"\n🛑 Adquisición interrumpida en el bloque {block_num}/{self.config['num_blocks']} ({progress_percent:.1f}%)")

    def _report_block_progress(self, block_num: int, block_readings: List[float],
                             block_start_time: float):
        """Reporta el progreso del bloque"""
        block_time = time.time() - block_start_time
        sps = len(block_readings) / block_time if block_time > 0 else 0

        if self.config['infinite_mode']:
            print(f"✓ Bloque {block_num} completado: {len(block_readings)} muestras en {block_time:.3f}s (SPS: {sps:.1f})")
        else:
            progress_percent = ((block_num) / self.config['num_blocks']) * 100
            print(f"✓ Bloque {block_num}/{self.config['num_blocks']} ({progress_percent:.1f}%): {len(block_readings)} muestras en {block_time:.3f}s (SPS: {sps:.1f})")

    def _print_final_results(self, results: Dict):
        """Imprime los resultados finales"""
        completion_status = "interrumpida" if results['interrupted'] else "completada"
        completion_icon = "🛑" if results['interrupted'] else "✅"

        print(f"\n=== Adquisición {completion_status} ===")
        print(f"{completion_icon} Total de muestras: {results['total_samples']}")
        print(f"⏱️ Tiempo total: {results['total_time']:.3f} segundos")
        if results['total_time'] > 0:
            sps = results['total_samples'] / results['total_time']
            print(f"📊 SPS promedio: {sps:.1f}")
        print(f"💾 Datos guardados en: {results['csv_file']}")

        if results['interrupted'] and not self.config['infinite_mode']:
            progress_percent = (results['blocks_completed'] / self.config['num_blocks']) * 100
            print(f"📋 Bloques completados: {results['blocks_completed']}/{self.config['num_blocks']} ({progress_percent:.1f}%)")

def ciclo(num_ciclos, punto_inicio, punto_final, num_puntos_intermedios):
    setpoints = []
    for _ in range(num_ciclos):
        # Barrido ascendente (incluyendo punto inicial y final)
        for i in range(num_puntos_intermedios + 1):
            sp = punto_inicio + (punto_final - punto_inicio) * i / num_puntos_intermedios
            setpoints.append(round(sp, 3))
        # Barrido descendente (incluyendo punto final y punto inicial para igual número de puntos)
        for i in range(num_puntos_intermedios + 1):
            sp = punto_final - (punto_final - punto_inicio) * i / num_puntos_intermedios
            setpoints.append(round(sp, 3))
    return setpoints

def generar_setpoints(num_ciclos, punto_inicio, punto_final, num_puntos_intermedios, intermediate_mode, custom_points_text):
    """Genera lista de setpoints basada en el modo seleccionado"""
    if intermediate_mode == "manual":
        # Usar puntos personalizados
        try:
            # Parsear la cadena de puntos personalizados
            import ast
            custom_points = ast.literal_eval(custom_points_text)
            if not isinstance(custom_points, list) or len(custom_points) < 2:
                raise ValueError("Puntos personalizados deben ser una lista con al menos 2 elementos")

            # Convertir a float y redondear
            custom_points = [round(float(sp), 3) for sp in custom_points]

            # Para cada ciclo, aplicar los puntos personalizados tanto para subida como bajada
            setpoints = []
            for _ in range(num_ciclos):
                # Subida: usar los puntos en orden
                setpoints.extend(custom_points)
                # Bajada: usar los puntos en orden inverso (excluyendo el último punto de subida para evitar duplicado)
                setpoints.extend(list(reversed(custom_points[:-1])))

            return setpoints

        except (ValueError, SyntaxError) as e:
            logger.warning(f"Error parsing custom points '{custom_points_text}': {e}. Using automatic mode.")
            # Fallback a modo automático
            return ciclo(num_ciclos, punto_inicio, punto_final, num_puntos_intermedios)
    else:
        # Modo automático
        return ciclo(num_ciclos, punto_inicio, punto_final, num_puntos_intermedios)

def read_tiva(ser_tiva, keithley_acquirer, result):
    """Leer datos del TIVA de manera optimizada"""
    # Leer Keithley inmediatamente después de TIVA
    keithley_local_result = [None]
    read_keithley(keithley_acquirer, keithley_local_result)

    linea_raw = ser_tiva.readline().strip()
    if not linea_raw or len(linea_raw) < 12:
        result[:] = [None, None, None, keithley_local_result[0]]
        return

    # Función auxiliar para parsear valores de 2 bytes
    def parse_value(high_byte, low_byte):
        alto = (high_byte >> 4) & 0x0F
        bajo = high_byte & 0x0F
        alto1 = (low_byte >> 4) & 0x0F
        bajo1 = low_byte & 0x0F
        return alto * 0.1 + bajo * 0.01 + alto1 * 0.001 + bajo1 * 0.0001

    # Parsing optimizado de datos TIVA
    com_tiva_raw = parse_value(linea_raw[1], linea_raw[2]) + (linea_raw[3] >> 4 & 0x0F) * 0.00001 + (linea_raw[3] & 0x0F) * 0.000001
    com_tiva_filtrado = parse_value(linea_raw[6], linea_raw[7]) + (linea_raw[8] >> 4 & 0x0F) * 0.00001 + (linea_raw[8] & 0x0F) * 0.000001
    com_tiva_temp = (linea_raw[10] >> 4 & 0x0F) * 10 + (linea_raw[10] & 0x0F) + (linea_raw[11] >> 4 & 0x0F) * 0.1 + (linea_raw[11] & 0x0F) * 0.01

    # Aplicar signos de manera más eficiente
    if linea_raw[0] == 45:  # '-'
        com_tiva_raw = -com_tiva_raw
    if linea_raw[5] == 45:  # '-'
        com_tiva_filtrado = -com_tiva_filtrado

    result[:] = [com_tiva_raw, com_tiva_filtrado, com_tiva_temp, keithley_local_result[0]]

def stability_setpoint(ser_alicat, setpoint, threshold=0.002, expected_time=30, averaging_time=5):
    """Espera hasta que la presión se estabilice cerca del setpoint, verificando el promedio durante averaging_time"""
    start_time = time.time()
    pressures = []
    averaging_start = start_time
    while time.time() - start_time < expected_time:
        ser_alicat.write(b"A @ @\r")
        time.sleep(0.1)  # Pequeña espera para respuesta
        linea = ser_alicat.readline().decode('ascii', errors='ignore').strip()
        if not linea:
            continue
        campos = linea.split()
        if len(campos) >= 3:
            try:
                presion_actual = float(campos[1])
                pressures.append(presion_actual)
                current_time = time.time()
                if current_time - averaging_start >= averaging_time and len(pressures) > 0:
                    avg_pressure = sum(pressures) / len(pressures)
                    if abs(avg_pressure - setpoint) <= threshold:
                        ser_alicat.write(b"@@ A\r")
                        logger.info(f"Presión estabilizada - Promedio: {avg_pressure:.3f} kPA (setpoint: {setpoint:.3f})")
                        return True
                    else:
                        # Reset para nueva ventana de promediado
                        pressures = []
                        averaging_start = current_time
            except (ValueError, IndexError):
                continue
    logger.warning(f"Tiempo de espera excedido para estabilización de presión: {expected_time}s")
    return False

def stability_keithley_reference_to_tiva(ser_tiva, keithley_acquirer, threshold=0.0001, expected_time=30, averaging_time=20) -> bool:
    """Espera hasta que la tensión de TIVA se estabilice cerca de la referencia de Keithley, verificando el promedio durante averaging_time"""
    start_time = time.time()
    differences = []
    voltages = []
    averaging_start = start_time
    while time.time() - start_time < expected_time:
        # Leer TIVA y Keithley
        tiva_result = [None, None, None, None]
        read_tiva(ser_tiva, keithley_acquirer, tiva_result)
        com_tiva_raw, com_tiva_filtrado, com_tiva_temp, voltage_v = tiva_result

        if voltage_v is not None and com_tiva_filtrado is not None:
            diff = abs(com_tiva_filtrado - voltage_v)
            differences.append(diff)
            voltages.append(voltage_v)
            current_time = time.time()
            # print(current_time - averaging_start, averaging_time, len(differences))
            if current_time - averaging_start >= averaging_time and len(differences) > 0:
                avg_diff = sum(differences) / len(differences)
                print(f"Averaging completed: avg_diff={avg_diff:.6f} threshold={threshold:.6f}")
                if avg_diff <= threshold:
                    logger.info(f"Voltaje TIVA estabilizado - Promedio diff: {avg_diff:.6f} V")
                    return True
                else:
                    differences = []
                    voltages = []
                    averaging_start = current_time
        time.sleep(0.01)
    logger.warning(f"Tiempo de espera excedido para estabilización de voltaje: {expected_time}s")
    # Reset para nueva ventana de promediado
    return False

def read_alicat(ser_alicat, result):
    """Leer datos del Alicat de manera optimizada"""
    try:
        dato_alicat = ser_alicat.readline().decode('ascii', errors='ignore').strip()
        if not dato_alicat:
            result[:] = [None, None]
            return

        campos = dato_alicat.split()
        if len(campos) >= 3:
            try:
                result[:] = [float(campos[1]), float(campos[2])]
            except (ValueError, IndexError):
                result[:] = [None, None]
        else:
            result[:] = [None, None]
    except Exception:
        result[:] = [None, None]

def read_keithley(keithley_acquirer, result):
    """Leer datos del Keithley de manera optimizada"""
    try:
        block_readings = keithley_acquirer.acquire_block(1)
        result[0] = block_readings[0] if block_readings else None
    except Exception:
        result[0] = None

def acquisition_loop(params):
    global acquisition_running, acquisition_paused
    global logger
    global ser_tiva_global, ser_alicat_global, keithley_acquirer_global

    # Extraer parámetros
    setpoint_inicial = params['setpoint_inicial']
    setpoint_final = params['setpoint_final']
    setpoint_intervalo = params['setpoint_intervalo']
    num_puntos_intermedios = params['num_puntos_intermedios']
    num_ciclos = params['num_ciclos']
    intermediate_mode = params['intermediate_mode']
    custom_points_text = params['custom_points_text']
    stability_time = params['stability_time'] if params['enable_stability'] else 0
    file_label = params.get('file_label', 'Datos')  # Usar 'Datos' como valor por defecto

    # Preparar archivo CSV con timestamp actual y etiqueta personalizada
    csv_file = f"{file_label}_{time.strftime('%Y%m%d_%H%M%S')}.csv"
    file_exists = os.path.isfile(csv_file)
    csv_f = open(csv_file, "a", newline="")
    csv_writer = csv.writer(csv_f)

    if not file_exists:
        csv_writer.writerow(["Timestamp", "Sample", "Ciclo", "Fase", "TIVA Voltage (V)", "TIVA Voltage w/FPB(V)","KEITHLEY Voltage (V)", "TIVA Temp (C)", "Alicat Presion (kPA)", "Alicat Setpoint (kPA)", "Setpoint Enviado (kPA)"])
        logger.info(f"Archivo CSV creado: {csv_file}")

    # Inicializar conexiones seriales optimizadas
    ser_tiva = serial.Serial(port=tiva_port, baudrate=115200, timeout=0.01)
    ser_alicat = serial.Serial(port="COM5", baudrate=115200, bytesize=8, parity='N', stopbits=1, timeout=0.01)

    # Configurar Keithley
    keithley_acquirer = KeithleyAcquisition(keithley_config, logger)
    keithley_acquirer._connect_instrument()

    # Asignar a variables globales para acceso desde detener_adquisicion
    ser_tiva_global = ser_tiva
    ser_alicat_global = ser_alicat
    keithley_acquirer_global = keithley_acquirer

    # Generar lista de setpoints de manera optimizada
    setpoint_list = generar_setpoints(num_ciclos, setpoint_inicial, setpoint_final, num_puntos_intermedios, intermediate_mode, custom_points_text)
    logger.info(f"Setpoints generados: {setpoint_list}")
    # Calcular configuración de ciclos de manera más eficiente
    if intermediate_mode == "manual":
        custom_points = ast.literal_eval(custom_points_text)
        puntos_subida = len(custom_points)
        puntos_bajada = len(custom_points) - 1
    else:
        puntos_subida = puntos_bajada = num_puntos_intermedios + 1

    puntos_por_ciclo = puntos_subida + puntos_bajada

    ser_alicat.write(b"@@ A\r")  # Comando para iniciar comunicación

    # Inicializar variables de control
    current_setpoint_index = 0
    nuevo_setpoint = setpoint_list[0] if setpoint_list else setpoint_inicial
    time.sleep(0.5)  # Pequeña espera para asegurar que el comando se procese
    # Configurar setpoint inicial de manera optimizada
    ser_alicat.write(f"A S {nuevo_setpoint:.1f}\r".encode('ascii'))
    time.sleep(0.5)  # Pequeña espera para asegurar que el comando se procese
    
    # Espera de estabilización inicial usando métodos específicos
    if stability_time > 0:
        logger.info(f"Iniciando estabilización inicial para setpoint: {nuevo_setpoint:.1f} kPA")
        stability_setpoint(ser_alicat, nuevo_setpoint, threshold=0.002, expected_time=stability_time)
        while not stability_keithley_reference_to_tiva(ser_tiva, keithley_acquirer, threshold=0.0005, expected_time=stability_time, averaging_time=20):
            time.sleep(0.001)

    # Logging de inicio optimizado
    logger.info(f"Adquisición iniciada - Archivo: {csv_file}")
    logger.info(f"Configuración: {num_ciclos} ciclos, {num_puntos_intermedios} puntos intermedios, Setpoint inicial: {nuevo_setpoint:.1f} kPA")
    time.sleep(1)
    ultimo_ajuste = time.time()
    sample_counter = 0
    ser_alicat.write(b"A @ @\r")  # Comando para iniciar lecturas
    try:
        while acquisition_running:
            if acquisition_paused:
                continue

            sample_counter += 1
            timestamp = time.strftime('%H:%M:%S')
            current_time = time.time()

            # Cálculo optimizado de ciclo y fase
            ciclo_num = (current_setpoint_index // puntos_por_ciclo) + 1
            posicion_en_ciclo = current_setpoint_index % puntos_por_ciclo
            fase = "subida" if posicion_en_ciclo < puntos_subida else "bajada"

            # Cambio de setpoint optimizado
            if current_time - ultimo_ajuste >= setpoint_intervalo:
                if current_setpoint_index + 1 < len(setpoint_list):
                    current_setpoint_index += 1
                    nuevo_setpoint = setpoint_list[current_setpoint_index]

                    if stability_time > 0:
                        logger.info(f"Cambio de setpoint - Ciclo: {ciclo_num}, Fase: {fase}, Setpoint: {nuevo_setpoint:.1f} kPA")

                    # Comando optimizado
                    ser_alicat.write(b"@@ A\r")
                    time.sleep(0.05) 
                    ser_alicat.write(f"A S {nuevo_setpoint:.3f}\r".encode('ascii'))

                    # Espera de estabilización usando métodos específicos
                    if stability_time > 0:
                        logger.info(f"Iniciando estabilización para setpoint: {nuevo_setpoint:.1f} kPA")
                        # Estabilizar presión del Alicat
                        stability_setpoint(ser_alicat, nuevo_setpoint, threshold=0.002, expected_time=stability_time)
                        # Estabilizar voltaje TIVA respecto a Keithley
                        while not stability_keithley_reference_to_tiva(ser_tiva, keithley_acquirer, threshold=0.0005, expected_time=stability_time, averaging_time=20):
                            time.sleep(0.001)
                        ser_alicat.write(b"A @ @\r")
                else:
                    ser_alicat.write(b"@@ A\r")
                    logger.info("Secuencia de adquisición completada")
                    acquisition_running = False
                    continue

                ultimo_ajuste = time.time()
            
            # Lectura de datos optimizada con hilos
            tiva_result = [None, None, None, None]
            alicat_result = [None, None]

            # tiva_thread = threading.Thread(target=read_tiva, args=(ser_tiva, keithley_acquirer, tiva_result))
            # alicat_thread = threading.Thread(target=read_alicat, args=(ser_alicat, alicat_result))
            read_tiva(ser_tiva, keithley_acquirer, tiva_result)
            read_alicat(ser_alicat, alicat_result)
            # tiva_thread.start()
            # alicat_thread.start()
            # tiva_thread.join()
            # alicat_thread.join()

            # Desempaquetar resultados
            com_tiva_raw, com_tiva_filtrado, com_tiva_temp, voltage_v = tiva_result
            alicat_presion, alicat_setpoint = alicat_result

            # Validación y guardado optimizado usando funciones de utilidad
            if validar_datos(com_tiva_raw, com_tiva_filtrado, com_tiva_temp, alicat_presion, alicat_setpoint, voltage_v):
                # Filtro de picos optimizado
                if not (abs(com_tiva_filtrado) > 0.1 and abs(com_tiva_temp) > 28):
                    fila_csv = formatear_fila_csv(
                        timestamp, sample_counter, ciclo_num, fase,
                        alicat_presion, alicat_setpoint, nuevo_setpoint,
                        com_tiva_raw, com_tiva_filtrado, voltage_v, 
                        com_tiva_temp
                    )
                    csv_writer.writerow(fila_csv)
                else:
                    logger.warning(f"Pico detectado - Filtrado: {com_tiva_filtrado:.6f}, Temp: {com_tiva_temp:.6f}")
            else:
                logger.warning("Datos incompletos - algunos sensores no respondieron")

    except Exception as e:
        logger.error(f"Error en adquisición: {e}")
    finally:
        # Limpieza optimizada de recursos
        if ser_tiva_global:
            ser_tiva_global.close()
            ser_tiva_global = None
        if ser_alicat_global:
            ser_alicat_global.close()
            ser_alicat_global = None
        csv_f.close()
        if keithley_acquirer_global:
            keithley_acquirer_global._disconnect_instrument()
            keithley_acquirer_global = None
        logger.info("Adquisición finalizada - Recursos liberados")

def iniciar_adquisicion(params):
    """Iniciar adquisición de manera optimizada"""
    global acquisition_running, thread_acquisition
    if not acquisition_running:
        acquisition_running = True
        thread_acquisition = threading.Thread(target=acquisition_loop, args=(params,))
        thread_acquisition.start()
        print("Adquisición iniciada.")

def formatear_fila_csv(timestamp, sample, ciclo, fase, alicat_presion, alicat_setpoint, nuevo_setpoint, *valores):
    """Formatear fila CSV de manera optimizada"""
    return [timestamp, sample, ciclo, fase] + [f"{v:.6f}" if isinstance(v, (int, float)) and v is not None else str(v) for v in valores] + [alicat_presion, alicat_setpoint, nuevo_setpoint]

def detener_adquisicion():
    """Detener adquisición de manera optimizada"""
    global acquisition_running, thread_acquisition
    global ser_tiva_global, ser_alicat_global, keithley_acquirer_global
    acquisition_running = False
    if thread_acquisition:
        thread_acquisition.join()
    # Cerrar comunicaciones seriales
    if ser_tiva_global:
        ser_tiva_global.close()
        ser_tiva_global = None
    if ser_alicat_global:
        ser_alicat_global.write(b"@@ A\r")
        ser_alicat_global.close()
        ser_alicat_global = None
    if keithley_acquirer_global:
        keithley_acquirer_global._disconnect_instrument()
        keithley_acquirer_global = None
    print("Adquisición detenida.")

def pausar_reanudar_adquisicion():
    """Pausar/reanudar adquisición de manera optimizada"""
    global acquisition_paused
    acquisition_paused = not acquisition_paused
    print("Adquisición pausada." if acquisition_paused else "Adquisición reanudada.")

def validar_datos(*valores):
    """Validar que todos los valores no sean None de manera optimizada"""
    return all(v is not None for v in valores)

def calcular_promedio(valores):
    """Calculapromedio de valores válidos de manera optimizada"""
    valores_validos = [v for v in valores if v is not None]
    return sum(valores_validos) / len(valores_validos) if valores_validos else None
