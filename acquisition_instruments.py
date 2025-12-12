import serial # permite comunicación serial
import time # para manejo de tiempos
import csv # para manejo de archivos CSV
import os # para verificar existencia de archivos
import threading # Permite ejecutar la adquisición en un hilo separado para no bloquear la interfaz gráfica
import tkinter as tk # Permite crear la ventana gráfica y los botones de control
import logging
import struct
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

# === TABLA CRC-16-CCITT ===
crc16_table = [
    0x0000,0x1021,0x2042,0x3063,0x4084,0x50A5,0x60C6,0x70E7,0x8108,0x9129,0xA14A,0xB16B,0xC18C,0xD1AD,0xE1CE,0xF1EF,
    0x1231,0x0210,0x3273,0x2252,0x52B5,0x4294,0x72F7,0x62D6,0x9339,0x8318,0xB37B,0xA35A,0xD3BD,0xC39C,0xF3FF,0xE3DE,
    0x2462,0x3443,0x0420,0x1401,0x64E6,0x74C7,0x44A4,0x5485,0xA56A,0xB54B,0x8528,0x9509,0xE5EE,0xF5CF,0xC5AC,0xD58D,
    0x3653,0x2672,0x1611,0x0630,0x76D7,0x66F6,0x5695,0x46B4,0xB75B,0xA77A,0x9719,0x8738,0xF7DF,0xE7FE,0xD79D,0xC7BC,
    0x48C4,0x58E5,0x6886,0x78A7,0x0840,0x1861,0x2802,0x3823,0xC9CC,0xD9ED,0xE98E,0xF9AF,0x8948,0x9969,0xA90A,0xB92B,
    0x5AF5,0x4AD4,0x7AB7,0x6A96,0x1A71,0x0A50,0x3A33,0x2A12,0xDBFD,0xCBDC,0xFBBF,0xEB9E,0x9B79,0x8B58,0xBB3B,0xAB1A,
    0x6CA6,0x7C87,0x4CE4,0x5CC5,0x2C22,0x3C03,0x0C60,0x1C41,0xEDAE,0xFD8F,0xCDEC,0xDDCD,0xAD2A,0xBD0B,0x8D68,0x9D49,
    0x7E97,0x6EB6,0x5ED5,0x4EF4,0x3E13,0x2E32,0x1E51,0x0E70,0xFF9F,0xEFBE,0xDFDD,0xCFFC,0xBF1B,0xAF3A,0x9F59,0x8F78,
    0x9188,0x81A9,0xB1CA,0xA1EB,0xD10C,0xC12D,0xF14E,0xE16F,0x1080,0x00A1,0x30C2,0x20E3,0x5004,0x4025,0x7046,0x6067,
    0x83B9,0x9398,0xA3FB,0xB3DA,0xC33D,0xD31C,0xE37F,0xF35E,0x02B1,0x1290,0x22F3,0x32D2,0x4235,0x5214,0x6277,0x7256,
    0xB5EA,0xA5CB,0x95A8,0x8589,0xF56E,0xE54F,0xD52C,0xC50D,0x34E2,0x24C3,0x14A0,0x0481,0x7466,0x6447,0x5424,0x4405,
    0xA7DB,0xB7FA,0x8799,0x97B8,0xE75F,0xF77E,0xC71D,0xD73C,0x26D3,0x36F2,0x0691,0x16B0,0x6657,0x7676,0x4615,0x5634,
    0xD94C,0xC96D,0xF90E,0xE92F,0x99C8,0x89E9,0xB98A,0xA9AB,0x5844,0x4865,0x7806,0x6827,0x18C0,0x08E1,0x3882,0x28A3,
    0xCB7D,0xDB5C,0xEB3F,0xFB1E,0x8BF9,0x9BD8,0xABBB,0xBB9A,0x4A75,0x5A54,0x6A37,0x7A16,0x0AF1,0x1AD0,0x2AB3,0x3A92,
    0xFD2E,0xED0F,0xDD6C,0xCD4D,0xBDAA,0xAD8B,0x9DE8,0x8DC9,0x7C26,0x6C07,0x5C64,0x4C45,0x3CA2,0x2C83,0x1CE0,0x0CC1,
    0xEF1F,0xFF3E,0xCF5D,0xDF7C,0xAF9B,0xBFBA,0x8FD9,0x9FF8,0x6E17,0x7E36,0x4E55,0x5E74,0x2E93,0x3EB2,0x0ED1,0x1EF0
]

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
        self.csv_writer.writerow(['Block', 'Sample_In_Block', 'Global_Sample', 'Current_A', 'Timestamp'])

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

# === FUNCIONES CRC ===
def calcular_crc16_ccitt(data: bytes) -> int:
    crc = 0xFFFF
    for b in data:
        crc = (crc << 8) ^ crc16_table[( (crc >> 8) ^ b) & 0xFF]
    return crc & 0xFFFF 

def checksum_xor(data: bytes) -> int:
    cs = 0
    for b in data:
        cs ^= b
    return cs

def read_tiva_simple(ser_tiva, keithley_acquirer, result):
    """
    Lee datos del TIVA usando el nuevo protocolo UART simple y Keithley de forma sincronizada.

    Protocolo: [0xAA] [4 bytes float] [1 byte XOR checksum] [0x41]

    Args:
        ser_tiva: Puerto serial del TIVA
        keithley_acquirer: Instancia del adquiridor Keithley
        result: Lista donde se almacenarán los resultados [valor_float, keithley_voltage]
    """
    # Leer Keithley inmediatamente
    keithley_local_result = [None]
    read_keithley(keithley_acquirer, keithley_local_result)

    # Limpiar buffer antes de sincronizar
    ser_tiva.reset_input_buffer()

    # -------- 1. Sincronización con header 0xAA --------
    sync_attempts = 0
    max_sync_attempts = 500

    while sync_attempts < max_sync_attempts:
        sync_attempts += 1
        byte = ser_tiva.read(1)
        if byte == b'\xAA':
            break
    else:
        # No se encontró sincronización
        logger.warning("No se pudo sincronizar con header TIVA (0xAA) después de múltiples intentos")
        result[:] = [None, keithley_local_result[0]]
        return

    # -------- 2. Leer los 6 bytes restantes (4 float + 1 checksum + 1 end) --------
    remaining = ser_tiva.read(6)
    if len(remaining) != 6:
        logger.warning(f"Paquete TIVA incompleto: {len(remaining)} bytes (esperado 6)")
        result[:] = [None, keithley_local_result[0]]
        return

    packet = b'\xAA' + remaining  # Paquete completo: 7 bytes

    # -------- 3. Verificar estructura --------
    if packet[-1] != 0x41:
        logger.warning(f"Byte de fin TIVA incorrecto: 0x{packet[-1]:02X} (esperado 0x41)")
        result[:] = [None, keithley_local_result[0]]
        return

    # -------- 4. Extraer payload y checksum --------
    payload = packet[1:5]  # 4 bytes del float
    checksum_recibido = packet[5]

    # -------- 5. Calcular checksum --------
    checksum_calculado = checksum_xor(payload)

    if checksum_calculado != checksum_recibido:
        logger.warning(f"Checksum TIVA ERROR → Recibido: 0x{checksum_recibido:02X} | Calculado: 0x{checksum_calculado:02X}")
        result[:] = [None, keithley_local_result[0]]
        return

    # -------- 6. Desempaquetar el float --------
    try:
        valor = struct.unpack('<f', payload)[0]
        result[:] = [valor, keithley_local_result[0]]
    except struct.error as e:
        logger.error(f"Error desempaquetando float TIVA: {e}")
        result[:] = [None, keithley_local_result[0]]

def read_tiva(ser_tiva, keithley_acquirer, result):
    """
    Lee datos del TIVA usando sincronización con header 0xAA 0x55 y Keithley de forma sincronizada.

    Args:
        ser_tiva: Puerto serial del TIVA
        keithley_acquirer: Instancia del adquiridor Keithley
        result: Lista donde se almacenarán los resultados [v_dif, v_a, v_b, temp, keithley_voltage]
    """
    # Leer Keithley inmediatamente después de TIVA
    keithley_local_result = [None]
    read_keithley(keithley_acquirer, keithley_local_result)

    # -------- 1. Sincronización con header 0xAA 0x55 --------
    sync_attempts = 0
    max_sync_attempts = 100  # Evitar bucle infinito
    
    ser_tiva.reset_input_buffer()  # Limpiar buffer antes de sincronizar

    while sync_attempts < max_sync_attempts:
        sync_attempts += 1
        if ser_tiva.read(1) == b'\xAA':
            if ser_tiva.read(1) == b'\x55':
                break
    else:
        # No se encontró sincronización
        logger.warning("No se pudo sincronizar con header TIVA después de múltiples intentos")
        result[:] = [None, None, None, None, None, keithley_local_result[0]]
        return

    # -------- 2. Leer los 26 bytes completos (24 + 2 CRC) --------
    packet = ser_tiva.read(26)
    if len(packet) != 26:
        logger.warning(f"Paquete TIVA incompleto: {len(packet)} bytes (esperado 26)")
        result[:] = [None, None, None, None, None, keithley_local_result[0]]
        return

    # -------- 3. Separar payload y CRC --------
    payload = packet[:24]        # 6 floats = 24 bytes
    crc_received = struct.unpack('<H', packet[24:26])[0]

    # -------- 4. Verificar CRC --------
    crc_calculated = calcular_crc16_ccitt(payload)

    if crc_calculated != crc_received:
        logger.warning(f"CRC TIVA inválido - Recibido: 0x{crc_received:04X}, Calculado: 0x{crc_calculated:04X}")
        result[:] = [None, None, None, None, None, keithley_local_result[0]]
        return

    # -------- 5. Desempaquetar los 6 floats --------
    try:
        v_dif, v_a, v_b, temp, comp, i_exc = struct.unpack('<6f', payload)
        result[:] = [v_dif, v_a, v_b, temp, i_exc, keithley_local_result[0]]
    except struct.error as e:
        logger.error(f"Error desempaquetando datos TIVA: {e}")
        logger.debug(f"Payload: {payload.hex()}")
        result[:] = [None, None, None, None, None, keithley_local_result[0]]

def stability_setpoint(ser_alicat, setpoint, threshold=0.002, expected_time=30, averaging_time=5):
    """Espera hasta que la presión se estabilice cerca del setpoint, verificando el promedio durante averaging_time.
    Una vez encontrada la estabilidad, debe mantenerla al menos 3 segundos; de lo contrario, repite."""
    start_time = time.time()
    pressures = []
    averaging_start = start_time
    stability_start_time = None
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
                        if stability_start_time is None:
                            stability_start_time = current_time
                            logger.info(f"Estabilidad inicial detectada - Promedio: {avg_pressure:.3f} kPA (setpoint: {setpoint:.3f})")
                        elif current_time - stability_start_time >= 3.0:
                            ser_alicat.write(b"@@ A\r")
                            logger.info(f"Presión estabilizada y mantenida por 3s - Promedio: {avg_pressure:.3f} kPA (setpoint: {setpoint:.3f})")
                            return True
                        # Continuar verificando durante los 3 segundos
                    else:
                        # Reset si sale del threshold
                        if stability_start_time is not None:
                            logger.debug(f"Estabilidad perdida - Promedio: {avg_pressure:.3f} kPA (setpoint: {setpoint:.3f})")
                        pressures = []
                        averaging_start = current_time
                        stability_start_time = None
            except (ValueError, IndexError):
                continue
    logger.warning(f"Tiempo de espera excedido para estabilización de presión: {expected_time}s")
    return False

def calcular_valor_teorico(T, P):
    # V(T,P) = [4.3435 - 0.008760*(T-20.0)]*P + [-7.3130 + 0.015086*(T-20.0)] mV
    # Convertir mV a V: dividir por 1000
    temp_offset = T - 20.0
    Vdif_teorico = (4.3435 - 0.00876 * temp_offset) * P + (-7.313 + 0.015086 * temp_offset)
    return Vdif_teorico / 1000

def calcular_P_from_V_T(V, T):
    #P(T, V) = \frac{ V - \left[ -7.3130 + 0.015086(T - 20.0) \right] }{ 4.3435 - 0.008760(T - 20.0) }
    temp_offset = T - 20.0
    numerator = V - (-7.313 + 0.015086 * temp_offset)
    denominator = 4.3435 - 0.00876 * temp_offset
    if denominator == 0:
        return None
    return numerator / denominator

def stability_tiva_reference_to_calculated(ser_tiva, keithley_acquirer, threshold=0.0001, expected_time=30, averaging_time=20, current_press=None) -> bool:
    """
    Espera hasta que el voltaje diferencial del TIVA se estabilice respecto al valor calculado teóricamente.
    Una vez encontrada la estabilidad, debe mantenerla al menos 3 segundos; de lo contrario, repite.

    La fórmula utilizada es: V(T,P) = [4.3435 - 0.008760*(T-20.0)]*P + [-7.3130 + 0.015086*(T-20.0)] mV
    Convertida a voltios: V(T,P) = [0.0043435 - 0.00008760*(T-20.0)]*P + [-0.007313 + 0.000015086*(T-20.0)]
    """
    if current_press is None:
        logger.error("Parámetro current_press no puede ser None")
        return False

    start_time = time.time()
    tiva_readings = []  # Lista para almacenar lecturas válidas (dif, temp)
    min_samples_for_stability = 100  # Número mínimo de muestras para considerar estabilidad
    stability_start_time = None

    while time.time() - start_time < expected_time:
        try:
            # Leer datos del TIVA
            tiva_result = [None, None, None, None, None]
            read_tiva(ser_tiva, keithley_acquirer, tiva_result)
            com_tiva_dif = tiva_result[0]
            com_tiva_temp = tiva_result[3]  # Temperatura del TIVA
            if com_tiva_dif is not None and com_tiva_temp is not None:
                # Almacenar par (voltaje_dif, temperatura)
                tiva_readings.append((com_tiva_dif, com_tiva_temp))

                # Verificar estabilidad cada averaging_time segundos
                current_time = time.time()
                if len(tiva_readings) >= min_samples_for_stability:
                    # Tomar las últimas lecturas para el promedio
                    recent_readings = tiva_readings[-min_samples_for_stability:]

                    # Calcular promedio de voltaje diferencial
                    avg_dif = sum(r[0] for r in recent_readings) / len(recent_readings)
                    avg_temp = sum(r[1] for r in recent_readings) / len(recent_readings)

                    calculated_dif = calcular_valor_teorico(avg_temp, current_press)

                    # Verificar si la diferencia está dentro del threshold
                    diff_from_expected = abs((calculated_dif) - avg_dif)
                    print(f"Medido: {avg_dif:.6f}V, Esperado: {calculated_dif:.6f}V, Dif: {diff_from_expected:.6f}V at P: {current_press:.3f}kPa, T: {avg_temp:.1f}°C, Muestras: {len(tiva_readings)}")
                    # logger.debug(f"Medido: {avg_dif:.6f}V, Esperado: {calculated_dif:.6f}V, Dif: {diff_from_expected:.6f}V at P: {current_press:.3f}kPa, T: {avg_temp:.1f}°C, Muestras: {len(tiva_readings)}")
                    if diff_from_expected < threshold:
                        if stability_start_time is None:
                            stability_start_time = current_time
                            logger.info(f"Estabilidad TIVA inicial detectada - Medido: {avg_dif:.6f}V, Esperado: {calculated_dif:.6f}V, Dif: {diff_from_expected:.6f}V")
                        elif current_time - stability_start_time >= 3.0:
                            logger.info(f"Voltaje TIVA estabilizado y mantenido por 3s - Medido: {avg_dif:.6f}V, "
                                      f"Esperado: {calculated_dif:.6f}V, "
                                      f"Diferencia: {diff_from_expected:.6f}V (T: {avg_temp:.1f}°C, P: {current_press:.3f}kPa)")
                            return True
                        # Continuar verificando durante los 3 segundos
                    else:
                        # Reset si sale del threshold
                        if stability_start_time is not None:
                            logger.debug(f"Estabilidad TIVA perdida - Medido: {avg_dif:.6f}V, Esperado: {calculated_dif:.6f}V, Dif: {diff_from_expected:.6f}V")
                        tiva_readings = []
                        stability_start_time = None
            else:
                tiva_readings = []
                stability_start_time = None

        except Exception as e:
            logger.error(f"Error en estabilidad TIVA vs calculado: {e}")
            return False
    logger.warning(f"Tiempo de espera excedido para estabilización TIVA ({expected_time}s) - "
                  f"Presión: {current_press:.3f}kPa, Muestras: {len(tiva_readings)}")
    return False

def stability_tiva_reference_to_keithley(ser_tiva, keithley_acquirer, threshold=0.0001, expected_time=30, averaging_time=20) -> bool:
    """
    Espera hasta que el voltaje diferencial del TIVA se estabilice respecto a la lectura del Keithley.
    Una vez encontrada la estabilidad, debe mantenerla al menos 3 segundos; de lo contrario, repite.
    """
    start_time = time.time()
    tiva_readings = []  # Lista para almacenar lecturas válidas (dif, temp)
    min_samples_for_stability = 100  # Número mínimo de muestras para considerar estabilidad
    stability_start_time = None

    while time.time() - start_time < expected_time:
        try:
            # Leer datos del TIVA
            tiva_result = [None, None, None, None, None, None]
            read_tiva(ser_tiva, keithley_acquirer, tiva_result)
            com_tiva_dif = tiva_result[0]

            # Leer Keithley
            keithley_result = [None]
            read_keithley(keithley_acquirer, keithley_result)
            keithley_voltage = keithley_result[0]

            if com_tiva_dif is not None and keithley_voltage is not None:
                # Almacenar par (voltaje_dif, voltaje_keithley)
                tiva_readings.append((com_tiva_dif, keithley_voltage))
                # Verificar estabilidad cada averaging_time segundos
                current_time = time.time()
                if len(tiva_readings) >= min_samples_for_stability:
                    # Tomar las últimas lecturas para el promedio
                    recent_readings = tiva_readings[-min_samples_for_stability:]

                    # Calcular promedios
                    avg_dif = sum(r[0] for r in recent_readings) / len(recent_readings)
                    avg_keithley = sum(r[1] for r in recent_readings) / len(recent_readings)

                    # Verificar si la diferencia está dentro del threshold
                    diff_from_expected = abs(avg_keithley - avg_dif)
                    # print(f"TIVA Dif: {avg_dif:.6f}V, Keithley: {avg_keithley:.6f}V, Dif: {diff_from_expected:.6f}V, Muestras: {len(tiva_readings)}")
                    if diff_from_expected < threshold:
                        if stability_start_time is None:
                            stability_start_time = current_time
                            logger.info(f"Estabilidad TIVA-Keithley inicial detectada - TIVA Dif: {avg_dif:.6f}V, Keithley: {avg_keithley:.6f}V, Dif: {diff_from_expected:.6f}V")
                        elif current_time - stability_start_time >= 3.0:
                            logger.info(f"Voltaje TIVA-Keithley estabilizado y mantenido por 3s - TIVA Dif: {avg_dif:.6f}V, "
                                      f"Keithley: {avg_keithley:.6f}V, "
                                      f"Diferencia: {diff_from_expected:.6f}V")
                            return True
                        # Continuar verificando durante los 3 segundos
                    else:
                        # Reset si sale del threshold
                        if stability_start_time is not None:
                            logger.debug(f"Estabilidad TIVA-Keithley perdida - TIVA Dif: {avg_dif:.6f}V, Keithley: {avg_keithley:.6f}V, Dif: {diff_from_expected:.6f}V")
                        tiva_readings = []
                        stability_start_time = None
            else:
                tiva_readings = []
                stability_start_time = None
        except Exception as e:
            logger.error(f"Error en estabilidad TIVA-Keithley: {e}")
            return False
    logger.warning(f"Tiempo de espera excedido para estabilización TIVA-Keithley ({expected_time}s) - Muestras: {len(tiva_readings)}")
    return False

def counts_to_voltage_32_bits(counts):
    """Convierte counts del Keithley a voltaje en voltios"""
    # Asumiendo configuración de rango 5V y resolución de 32 bits PGA 32
    den = 32*(2**32 - 1)  # Denominador para conversión
    voltage = (counts / den) * 5.0  # 2^32 - 1 = 4294967295
    return voltage

def stability_tiva_reference_to_keithley_simple(ser_tiva, keithley_acquirer, threshold=0.0001, expected_time=30, averaging_time=20) -> bool:

    # Inicializar variables
    tiva_readings = []
    stability_start_time = None
    min_samples_for_stability = 100  # Número mínimo de muestras para considerar estabilidad
    start_time = time.time()

    while time.time() - start_time < expected_time:
        try:
            # Leer datos del TIVA
            tiva_result = [None, None]
            read_tiva_simple(ser_tiva, keithley_acquirer, tiva_result)
            com_tiva_dif = counts_to_voltage_32_bits(tiva_result[0])
            # print(f"TIVA Counts: {tiva_result[0]}, Voltaje Dif: {com_tiva_dif:.6f}V")

            # Leer Keithley
            keithley_result = [None]
            read_keithley(keithley_acquirer, keithley_result)
            keithley_voltage = keithley_result[0]

            # print(f"TIVA Dif: {com_tiva_dif:.6f}V, Keithley: {keithley_voltage:.6f}V")

            if com_tiva_dif is not None and keithley_voltage is not None:
                # Almacenar par (voltaje_dif, voltaje_keithley)
                tiva_readings.append((com_tiva_dif, keithley_voltage))
                # Verificar estabilidad cada averaging_time segundos
                current_time = time.time()
                if len(tiva_readings) >= min_samples_for_stability:
                    # Tomar las últimas lecturas para el promedio
                    recent_readings = tiva_readings[-min_samples_for_stability:]

                    # Calcular promedios
                    avg_dif = sum(r[0] for r in recent_readings) / len(recent_readings)
                    avg_keithley = sum(r[1] for r in recent_readings) / len(recent_readings)

                    # Verificar si la diferencia está dentro del threshold
                    diff_from_expected = abs(avg_keithley - avg_dif)
                    if diff_from_expected < threshold:
                        if stability_start_time is None:
                            stability_start_time = current_time
                            logger.info(f"Estabilidad TIVA-Keithley inicial detectada - TIVA Dif: {avg_dif:.6f}V, Keithley: {avg_keithley:.6f}V, Dif: {diff_from_expected:.6f}V")
                        elif current_time - stability_start_time >= 3.0:
                            logger.info(f"Voltaje TIVA-Keithley estabilizado y mantenido por 3s - TIVA Dif: {avg_dif:.6f}V, "
                                      f"Keithley: {avg_keithley:.6f}V, "
                                      f"Diferencia: {diff_from_expected:.6f}V")
                            return True
                        # Continuar verificando durante los 3 segundos
                    else:
                        # Reset si sale del threshold
                        if stability_start_time is not None:
                            logger.debug(f"Estabilidad TIVA-Keithley perdida - TIVA Dif: {avg_dif:.6f}V, Keithley: {avg_keithley:.6f}V, Dif: {diff_from_expected:.6f}V")
                        tiva_readings = []
                        stability_start_time = None
            else:
                tiva_readings = []
                stability_start_time = None
        except Exception as e:
            logger.error(f"Error en estabilidad TIVA-Keithley: {e}")
            return False
    logger.warning(f"Tiempo de espera excedido para estabilización TIVA-Keithley ({expected_time}s) - Muestras: {len(tiva_readings)}")
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
        csv_writer.writerow(["Timestamp", "Sample", "Ciclo", "Fase", "Bridge VAB (V)", "KEITHLEY Voltaje (V)", "Bridge VA (V)", "Bridge VB (V)", "Bridge Current (A)", "TIVA Temp (C)", "Alicat Presion (kPA)", "Alicat Setpoint (kPA)", "Setpoint Enviado (kPA)"])
        logger.info(f"Archivo CSV creado: {csv_file}")
   
    # if not file_exists:
    #     csv_writer.writerow(["Timestamp", "Sample", "Ciclo", "Fase", "Bridge VAB (V)", "KEITHLEY Voltaje (V)", "TIVA Temp (C)", "Alicat Presion (kPA)", "Alicat Setpoint (kPA)", "Setpoint Enviado (kPA)"])
    #     logger.info(f"Archivo CSV creado: {csv_file}")

    # Inicializar conexiones seriales optimizadas
    ser_tiva = serial.Serial(port=tiva_port, 
            baudrate=230400, 
            timeout=1.0, 
            bytesize=serial.EIGHTBITS,
            parity=serial.PARITY_NONE,
            stopbits=serial.STOPBITS_ONE,
            xonxoff=False)
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
        while not stability_setpoint(ser_alicat, nuevo_setpoint, threshold=0.002, expected_time=stability_time):
            time.sleep(0.01)
        while not stability_tiva_reference_to_keithley(ser_tiva, keithley_acquirer, threshold=0.0001, expected_time=stability_time, averaging_time=20):
            time.sleep(0.01)

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

            elapsed_time = time.time() - ultimo_ajuste
            current_time = time.time()

            # Cálculo optimizado de ciclo y fase
            ciclo_num = (current_setpoint_index // puntos_por_ciclo) + 1
            posicion_en_ciclo = current_setpoint_index % puntos_por_ciclo
            fase = "subida" if posicion_en_ciclo < puntos_subida else "bajada"

            # Cambio de setpoint optimizado
            if current_time - ultimo_ajuste >= setpoint_intervalo:
                time.sleep(1)  # Pequeña espera antes de cambiar setpoint
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
                        while not stability_setpoint(ser_alicat, nuevo_setpoint, threshold=0.002, expected_time=stability_time):
                            time.sleep(0.01)
                        # Estabilizar voltaje TIVA respecto a Keithley
                        while not stability_tiva_reference_to_keithley(ser_tiva, keithley_acquirer, threshold=0.0001, expected_time=stability_time, averaging_time=20):
                            time.sleep(0.01)
                        ser_alicat.write(b"A @ @\r")
                else:
                    ser_alicat.write(b"@@ A\r")
                    logger.info("Secuencia de adquisición completada")
                    acquisition_running = False
                    continue

                ultimo_ajuste = time.time()
            
            # Lectura de datos optimizada con hilos
            # tiva_result = [None, None, None, None, None, None]
            tiva_result = [None, None]
            alicat_result = [None, None]

            read_tiva(ser_tiva, keithley_acquirer, tiva_result)
            read_alicat(ser_alicat, alicat_result)

            # Desempaquetar resultados
            com_tiva_dif, com_tiva_va, com_tiva_vb, com_tiva_temp, com_tiva_current, keithley_voltage = tiva_result

            # com_tiva_dif, keithley_voltage = tiva_result
            # com_tiva_va, com_tiva_vb, com_tiva_temp, com_tiva_current = None, None, None, None  # Valores no leídos en esta versión simplificada

            alicat_presion, alicat_setpoint = alicat_result
            # bridege_vab_calculado = calcular_valor_teorico(com_tiva_temp, alicat_presion) if com_tiva_temp is not None and alicat_presion is not None else None
            # presion_calculada = calcular_P_from_V_T(com_tiva_dif, com_tiva_temp) if com_tiva_dif is not None and com_tiva_temp is not None else None

            # Validación y guardado optimizado usando funciones de utilidad
            if validar_datos(com_tiva_dif, keithley_voltage, alicat_presion, alicat_setpoint):
                # "Timestamp", "Sample", "Ciclo", "Fase", "Bridge VAB (V)", "KEITHLEY Voltaje (V)", "Bridge VA (V)", "Bridge VB (V)", "Bridge Current (A)", "TIVA Temp (C)", "Alicat Presion (kPA)", "Alicat Setpoint (kPA)", "Setpoint Enviado (kPA)"
                fila_csv = formatear_fila_csv(
                    elapsed_time, sample_counter, ciclo_num, fase,
                    alicat_presion, alicat_setpoint, nuevo_setpoint,
                    com_tiva_dif, keithley_voltage,
                    com_tiva_va, com_tiva_vb, com_tiva_current,
                    com_tiva_temp
                )
                csv_writer.writerow(fila_csv)
            else:
                logger.warning(f"Datos inválidos detectados - Dif: {com_tiva_dif}, Temp: {com_tiva_temp}")
            # else:
            #     logger.warning("Datos incompletos - algunos sensores no respondieron")

    except Exception as e:
        logger.error(f"Error en adquisición: {e}")
    except KeyboardInterrupt:
        logger.info("Adquisición interrumpida por el usuario")
        detener_adquisicion()
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
    # "Timestamp", "Sample", "Ciclo", "Fase", "Bridge VAB (V)", "KEITHLEY Voltaje (V)", "Bridge VA (V)", "Bridge VB (V)", "Bridge Current (A)", "TIVA Temp (C)", "Alicat Presion (kPA)", "Alicat Setpoint (kPA)", "Setpoint Enviado (kPA)"
    return [f"{timestamp:.6f}", sample, ciclo, fase] + [f"{v:.6f}" if isinstance(v, (int, float)) and v is not None else str(v) for v in valores] + [alicat_presion, alicat_setpoint, nuevo_setpoint]

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
