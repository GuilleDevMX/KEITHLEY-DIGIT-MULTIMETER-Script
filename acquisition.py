"""
Módulo de adquisición de datos Keithley
"""
import pyvisa
import time
import csv
import threading
import logging
from datetime import datetime
from typing import List, Dict, Optional, Any
from contextlib import contextmanager

class KeithleyError(Exception):
    """Excepción base para errores del sistema Keithley"""
    pass


class KeithleyConnectionError(KeithleyError):
    """Error de conexión con el instrumento"""
    pass


class KeithleyAcquisitionError(KeithleyError):
    """Error durante la adquisición de datos"""
    pass


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