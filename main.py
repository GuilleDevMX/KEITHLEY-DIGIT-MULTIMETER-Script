#!/usr/bin/env python3
"""
Interfaz Gráfica para Sistema de Adquisición Integrada
Controla adquisición de datos con Keithley, Alicat y TIVA
"""
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import threading
import time
import os
import serial
import numpy as np
from datetime import datetime
from typing import List, Dict, Optional, Any
import logging
import csv
from scipy import stats
from contextlib import contextmanager
import pyvisa

# Importar librerías para visualización y exportación
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import pandas as pd
import openpyxl

# Importar módulos del sistema
# from acquisition import KeithleyAcquisition
from alicat_pid_calibration import AlicatController, AlicatPIDError
import acquisition_instruments  # Para acceder a las funciones existentes

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

class AcquisitionGUI:
    """Interfaz gráfica principal para el sistema de adquisición"""

    class TextHandler(logging.Handler):
        """Handler personalizado para redirigir logs al widget Text de Tkinter"""
        def __init__(self, text_widget):
            super().__init__()
            self.text_widget = text_widget

        def emit(self, record):
            msg = self.format(record)
            # Usar after para thread safety
            self.text_widget.after(0, lambda: self._insert_msg(msg))

        def _insert_msg(self, msg):
            self.text_widget.insert(tk.END, msg + '\n')
            self.text_widget.see(tk.END)

    def __init__(self, root):
        self.root = root
        self.root.title("Sistema de Adquisición Integrada - Keithley + Alicat + TIVA")
        # Mejorar tamaño inicial para mejor proporción
        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()
        window_width = min(int(screen_width * 0.85), 1200)  # 85% del ancho de pantalla, máx 1200
        window_height = min(int(screen_height * 0.85), 800)  # 85% del alto de pantalla, máx 800
        self.root.geometry(f"{window_width}x{window_height}")

        # Centrar la ventana en la pantalla
        x = (screen_width - window_width) // 2
        y = (screen_height - window_height) // 2
        self.root.geometry(f"+{x}+{y}")

        # Configurar comportamiento de redimensionamiento

        self.root.minsize(screen_width, screen_height)  # Tamaño máximo igual a pantalla

        # Variables de estado
        self.acquisition_running = False
        self.acquisition_paused = False
        self.calibration_running = False
        self.thread_acquisition = None
        self.thread_calibration = None
        self.monitoring_active = False  # Nueva variable para controlar el monitoreo

        # Variables de configuración
        self.setup_variables()

        # Configurar logging
        self.setup_logging()

        # Crear interfaz
        self.create_widgets()

        # Escanear puertos disponibles al inicio
        self.scan_serial_ports()

        # Configurar manejo de cierre de ventana
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)

    def on_closing(self):
        """Manejador para el cierre de la ventana - limpia todos los recursos"""
        self.logger.info("Iniciando limpieza de recursos...")

        try:
            # 1. Detener adquisición si está corriendo
            if self.acquisition_running:
                self.logger.info("Deteniendo adquisición...")
                self.stop_acquisition()

            # 2. Detener calibración si está corriendo
            if self.calibration_running:
                self.logger.info("Deteniendo calibración...")
                self.stop_calibration()

            # 3. Detener monitoreo de adquisición
            self.monitoring_active = False

            # 4. Esperar a que los threads terminen
            self.logger.info("Esperando que los threads terminen...")
            if self.thread_acquisition and self.thread_acquisition.is_alive():
                self.thread_acquisition.join(timeout=5.0)
            if self.thread_calibration and self.thread_calibration.is_alive():
                self.thread_calibration.join(timeout=5.0)

            # 4. Forzar detención de adquisición en el módulo si aún está corriendo
            try:
                if hasattr(acquisition_instruments, 'acquisition_running') and acquisition_instruments.acquisition_running:
                    acquisition_instruments.acquisition_running = False
                    if hasattr(acquisition_instruments, 'thread_acquisition') and acquisition_instruments.thread_acquisition:
                        acquisition_instruments.thread_acquisition.join(timeout=2.0)
                    self.logger.info("Adquisición en módulo acquisition_instruments forzadamente detenida")
            except Exception as e:
                self.logger.warning(f"Error forzando detención en módulo: {e}")

            # 5. Cerrar figuras de matplotlib
            self.logger.info("Cerrando figuras de matplotlib...")
            for fig in self.plot_figures:
                try:
                    plt.close(fig)
                except Exception as e:
                    self.logger.warning(f"Error cerrando figura matplotlib: {e}")
            self.plot_figures.clear()
            self.plot_canvases.clear()

            # 6. Limpiar figuras de análisis
            self.logger.info("Limpiando figuras de análisis...")
            try:
                # Limpiar todas las figuras almacenadas en analysis_results
                for analysis_type, results in self.analysis_results.items():
                    if isinstance(results, dict) and 'figures' in results:
                        figures = results.get('figures', [])
                        if isinstance(figures, list):
                            for fig in figures:
                                try:
                                    plt.close(fig)
                                except Exception as e:
                                    self.logger.warning(f"Error cerrando figura de análisis {analysis_type}: {e}")
                        elif hasattr(figures, 'close'):  # Si es una sola figura
                            try:
                                plt.close(figures)
                            except Exception as e:
                                self.logger.warning(f"Error cerrando figura única de análisis {analysis_type}: {e}")

                # Limpiar el diccionario de resultados de análisis
                self.analysis_results.clear()
                self.logger.info("Figuras de análisis limpiadas correctamente")

            except Exception as e:
                self.logger.warning(f"Error durante limpieza de figuras de análisis: {e}")

            # 7. Limpiar handlers de logging si es necesario
            try:
                for handler in self.logger.handlers[:]:
                    handler.close()
                    self.logger.removeHandler(handler)
            except Exception as e:
                self.logger.warning(f"Error cerrando handlers de logging: {e}")

            self.logger.info("Limpieza de recursos completada exitosamente")

        except Exception as e:
            self.logger.error(f"Error durante la limpieza de recursos: {e}")

        finally:
            # Destruir la ventana
            self.root.destroy()

    def setup_variables(self):
        """Inicializar variables de configuración"""
        # Parámetros de setpoint
        self.setpoint_inicial = tk.DoubleVar(value=0.0)
        self.setpoint_final = tk.DoubleVar(value=6.867)
        self.setpoint_intervalo = tk.IntVar(value=20)
        self.num_puntos_intermedios = tk.IntVar(value=2)
        self.num_ciclos = tk.IntVar(value=1)
        self.stability_time = tk.IntVar(value=20)
        self.enable_stability = tk.BooleanVar(value=True)

        # Etiqueta del archivo
        self.file_label = tk.StringVar(value="Datos")

        # Modo de puntos intermedios
        self.intermediate_mode = tk.StringVar(value="manual")  # "automatic" o "manual"
        self.custom_points_text = tk.StringVar(value="[0, 1, 2, 3, 4, 5, 6, 6.5, 6.8]")

        # Puertos seriales
        self.alicat_port = tk.StringVar(value="COM5")
        self.tiva_port = tk.StringVar(value="COM6")
        self.keithley_resource = tk.StringVar(value="")

        # Configuración serial avanzada
        self.alicat_serial_config = {
            'baudrate': 115200,
            'bytesize': serial.EIGHTBITS,
            'parity': serial.PARITY_NONE,
            'stopbits': serial.STOPBITS_ONE,
            'flowcontrol': 'None'
        }
        self.tiva_serial_config = {
            'baudrate': 230400,
            'timeout': 1.0,
            'bytesize': serial.EIGHTBITS,
            'parity': serial.PARITY_NONE,
            'stopbits': serial.STOPBITS_ONE,
            'flowcontrol': 'None'
        }

        # Estado de adquisición
        self.status_text = tk.StringVar(value="Sistema listo")

        # Variables para visualización
        self.current_csv_file = tk.StringVar(value="")
        self.csv_data = None
        self.plot_figures = []
        self.plot_canvases = []

        # Controladores de dispositivos
        self.alicat_controller = None
 
        # Variables para configuración PID del Alicat
        self.lca_mode = tk.StringVar(value="PD/PDF")
        self.pid_p_gain = tk.DoubleVar(value=0.0)
        self.pid_d_gain = tk.DoubleVar(value=0.0)
        self.pid_i_gain = tk.DoubleVar(value=0.0)

        # Variables para calibración
        self.calib_setpoint = tk.DoubleVar(value=1.0)
        self.calib_duration = tk.IntVar(value=20)

        # Variables para configuración Keithley
        self.experiment_label = tk.StringVar(value="integrated_acquisition")
        self.samples_per_count = tk.IntVar(value=1)
        self.nplc_cycles = tk.DoubleVar(value=1.0)
        self.infinite_mode = tk.BooleanVar(value=False)
        self.num_blocks = tk.IntVar(value=1)
        self.no_stats = tk.BooleanVar(value=False)
        self.output_dir = tk.StringVar(value=".")
        self.quiet = tk.BooleanVar(value=False)

        # Variables para análisis estadístico avanzado
        self.analysis_type = tk.StringVar(value="correlation")
        self.analysis_signal_1 = tk.StringVar(value="")
        self.analysis_signal_2 = tk.StringVar(value="")
        self.analysis_window_size = tk.IntVar(value=30)
        self.analysis_step_size = tk.IntVar(value=5)
        self.analysis_min_cycles = tk.IntVar(value=3)

        # Variables para almacenar datos de análisis
        self.analysis_results = {}  # Diccionario para almacenar resultados de análisis por tipo

    def setup_logging(self):
        """Configurar sistema de logging"""
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler('gui_acquisition.log'),
                logging.StreamHandler()
            ]
        )
        self.logger = logging.getLogger(__name__)

    def create_widgets(self):
        """Crear todos los widgets de la interfaz con estructura mejorada"""
        # Configurar estilo moderno
        self.setup_style()

        # Crear layout principal con sidebar
        self.create_main_layout()

        # Barra de estado mejorada
        self.create_status_bar()

    def setup_style(self):
        """Configurar estilo moderno para la interfaz"""
        style = ttk.Style()

        # Configurar colores y fuentes modernas
        style.configure('Modern.TFrame', background='#f5f5f5')
        style.configure('Sidebar.TFrame', background='#2c3e50')
        style.configure('Content.TFrame', background='white')

        # Configurar botones del sidebar con mejor espaciado
        style.configure('Sidebar.TButton',
                       background='#34495e',
                       foreground='white',
                       font=('Arial', 10, 'bold'),
                       padding=(15, 8))  # Más padding horizontal
        style.map('Sidebar.TButton',
                 background=[('active', '#3498db')])

        # Configurar headers con mejor jerarquía
        style.configure('Header.TLabel',
                       font=('Arial', 16, 'bold'),  # Más grande
                       foreground='#2c3e50')

        # Configurar secciones con mejor espaciado
        style.configure('Section.TLabelframe',
                       background='white',
                       borderwidth=1,
                       relief='solid')
        style.configure('Section.TLabelframe.Label',
                       font=('Arial', 12, 'bold'),  # Más grande
                       foreground='#34495e')

        # Configurar botones estándar
        style.configure('TButton', font=('Arial', 9), padding=(8, 4))

        # Configurar spinboxes y entradas
        style.configure('TSpinbox', font=('Arial', 9))
        style.configure('TEntry', font=('Arial', 9))

        # Configurar labels
        style.configure('TLabel', font=('Arial', 9))

    def create_main_layout(self):
        """Crear layout principal con sidebar de navegación"""
        # Frame principal
        main_frame = ttk.Frame(self.root, style='Modern.TFrame')
        main_frame.pack(fill=tk.BOTH, expand=True)

        # Sidebar de navegación (izquierda) - ancho responsivo
        screen_width = self.root.winfo_screenwidth()
        sidebar_width = min(int(screen_width * 0.18), 220)  # 18% del ancho de pantalla, máx 220px
        sidebar_width = max(sidebar_width, 180)  # mín 180px

        self.sidebar_frame = ttk.Frame(main_frame, style='Sidebar.TFrame', width=sidebar_width)
        self.sidebar_frame.pack(side=tk.LEFT, fill=tk.Y)
        self.sidebar_frame.pack_propagate(False)

        # Área de contenido (derecha)
        self.content_frame = ttk.Frame(main_frame, style='Content.TFrame')
        self.content_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)

        # Crear sidebar
        self.create_sidebar()

        # Crear área de contenido con notebook
        self.create_content_area()

    def create_sidebar(self):
        """Crear sidebar de navegación moderno"""
        # Título del sidebar
        title_frame = ttk.Frame(self.sidebar_frame, style='Sidebar.TFrame')
        title_frame.pack(fill=tk.X, pady=(20, 30))

        title_label = tk.Label(title_frame,
                              text="Sistema de\nAdquisición",
                              font=('Arial', 12, 'bold'),
                              fg='white',
                              bg='#2c3e50',
                              justify=tk.CENTER)
        title_label.pack()

        # Botones de navegación
        self.nav_buttons = {}

        nav_items = [
            ('control', '🎛️ Control\nAdquisición', 'Control de adquisición de datos'),
            ('calibration', '🔧 Calibración\nPID', 'Calibración de parámetros PID'),
            ('visualization', '📊 Visualización\nDatos', 'Visualización y análisis de datos'),
            ('analysis', '🔍 Análisis\nDetallado', 'Análisis estadístico avanzado'),
            ('export', '💾 Exportación\nDatos', 'Exportación de resultados')
        ]

        for nav_id, text, tooltip in nav_items:
            btn = tk.Button(self.sidebar_frame,
                           text=text,
                           font=('Arial', 9),
                           fg='white',
                           bg='#34495e',
                           activebackground='#3498db',
                           activeforeground='white',
                           bd=0,
                           padx=10,
                           pady=8,
                           command=lambda nid=nav_id: self.switch_content(nid))
            btn.pack(fill=tk.X, padx=5, pady=2)
            self.nav_buttons[nav_id] = btn

            # Tooltip
            self.create_tooltip(btn, tooltip)

        # Separador
        ttk.Separator(self.sidebar_frame, orient='horizontal').pack(fill=tk.X, pady=20)

        # Información del sistema
        system_frame = ttk.Frame(self.sidebar_frame, style='Sidebar.TFrame')
        system_frame.pack(fill=tk.X, padx=10, pady=10)

        tk.Label(system_frame,
                text="Estado:",
                font=('Arial', 8),
                fg='lightgray',
                bg='#2c3e50').pack(anchor=tk.W)

        self.sidebar_status = tk.Label(system_frame,
                                     text="Listo",
                                     font=('Arial', 8, 'bold'),
                                     fg='#2ecc71',
                                     bg='#2c3e50')
        self.sidebar_status.pack(anchor=tk.W)

    def create_tooltip(self, widget, text):
        """Crear tooltip para un widget"""
        def enter(event):
            self.tooltip = tk.Toplevel()
            self.tooltip.wm_overrideredirect(True)
            self.tooltip.wm_geometry(f"+{event.x_root+10}+{event.y_root+10}")

            label = tk.Label(self.tooltip, text=text, background="#ffffe0",
                           relief="solid", borderwidth=1, font=("Arial", 8))
            label.pack()

        def leave(event):
            if hasattr(self, 'tooltip'):
                self.tooltip.destroy()

        widget.bind('<Enter>', enter)
        widget.bind('<Leave>', leave)

    def create_content_area(self):
        """Crear área de contenido con notebook oculto inicialmente"""
        # Header del contenido
        self.content_header = ttk.Frame(self.content_frame, style='Content.TFrame')
        self.content_header.pack(fill=tk.X, padx=20, pady=(20, 10))

        self.content_title = ttk.Label(self.content_header,
                                      text="Panel de Control de Adquisición",
                                      style='Header.TLabel')
        self.content_title.pack(side=tk.LEFT)

        # Área de contenido principal
        self.content_main = ttk.Frame(self.content_frame, style='Content.TFrame')
        self.content_main.pack(fill=tk.BOTH, expand=True, padx=20, pady=(0, 20))

        # Crear páginas de contenido (inicialmente ocultas)
        self.content_pages = {}
        self.create_content_pages()

        # Mostrar página inicial
        self.switch_content('control')

    def create_content_pages(self):
        """Crear todas las páginas de contenido"""
        # Página de Control
        self.content_pages['control'] = self.create_control_page()

        # Página de Calibración
        self.content_pages['calibration'] = self.create_calibration_page()

        # Página de Visualización
        self.content_pages['visualization'] = self.create_visualization_page()

        # Página de Análisis
        self.content_pages['analysis'] = self.create_analysis_page()

        # Página de Exportación
        self.content_pages['export'] = self.create_export_page()

    def create_control_page(self):
        """Crear página de control de adquisición"""
        page = ttk.Frame(self.content_main, style='Content.TFrame')

        # Layout en dos columnas
        page.columnconfigure(0, weight=3)  # Columna izquierda: 3 partes
        page.columnconfigure(1, weight=1)  # Columna derecha: 1 parte
        page.rowconfigure(0, weight=1)

        left_frame = ttk.Frame(page)
        left_frame.grid(row=0, column=0, sticky=tk.NSEW, padx=(0, 10))

        right_frame = ttk.Frame(page)
        right_frame.grid(row=0, column=1, sticky=tk.NSEW, padx=(10, 0))

        # === SECCIÓN DE CONTROL (izquierda) ===
        control_section = ttk.LabelFrame(left_frame, text="🎛️ Control de Adquisición",
                                        style='Section.TLabelframe', padding=15)
        control_section.pack(fill=tk.X, pady=(0, 15))

        # Estado del sistema
        status_frame = ttk.Frame(control_section)
        status_frame.pack(fill=tk.X, pady=(0, 15))

        ttk.Label(status_frame, text="Estado:", font=('Arial', 10, 'bold')).grid(row=0, column=0, sticky=tk.W)
        ttk.Label(status_frame, textvariable=self.status_text, foreground='#2ecc71').grid(row=0, column=1, sticky=tk.W, padx=(10, 0))

        # Botones de control - mejor espaciado
        buttons_frame = ttk.Frame(control_section)
        buttons_frame.pack(pady=(10, 20))  # Más padding vertical

        self.btn_start = ttk.Button(buttons_frame, text="▶️ Iniciar Adquisición",
                                   command=self.start_acquisition, width=18)
        self.btn_start.grid(row=0, column=0, padx=8, pady=1)

        self.btn_pause = ttk.Button(buttons_frame, text="⏸️ Pausar/Reanudar",
                                   command=self.pause_resume_acquisition,
                                   state=tk.DISABLED, width=18)
        self.btn_pause.grid(row=0, column=1, padx=8, pady=1)

        self.btn_stop = ttk.Button(buttons_frame, text="⏹️ Detener Adquisición",
                                  command=self.stop_acquisition,
                                  state=tk.DISABLED, width=18)
        self.btn_stop.grid(row=0, column=2, padx=8, pady=1)

        # Etiqueta del archivo CSV
        file_label_frame = ttk.Frame(control_section)
        file_label_frame.pack(fill=tk.X, pady=(10, 15))

        ttk.Label(file_label_frame, text="Etiqueta del Archivo:", font=('Arial', 9, 'bold')).grid(row=0, column=0, sticky=tk.W, pady=2)
        ttk.Entry(file_label_frame, textvariable=self.file_label, width=45).grid(row=0, column=2, sticky=tk.W, padx=(10, 0))

        # === SECCIÓN DE PARÁMETROS (izquierda) ===
        params_section = ttk.LabelFrame(left_frame, text="⚙️ Parámetros de Setpoint",
                                       style='Section.TLabelframe', padding=15)
        params_section.pack(fill=tk.BOTH, expand=True)

        # Scrollable frame para parámetros - mejor configuración
        canvas = tk.Canvas(params_section, bg='white', highlightthickness=0)
        scrollbar = ttk.Scrollbar(params_section, orient=tk.VERTICAL, command=canvas.yview)
        scrollable_frame = ttk.Frame(canvas, style='Content.TFrame')

        scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )

        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        # Configurar scroll con mouse wheel
        def _on_mousewheel(event):
            canvas.yview_scroll(int(-1*(event.delta/120)), "units")
        canvas.bind_all("<MouseWheel>", _on_mousewheel)

        # Modo de puntos intermedios
        ttk.Label(scrollable_frame, text="Modo Puntos Intermedios:").grid(row=1, column=0, sticky=tk.W, pady=3)

        mode_frame = ttk.Frame(scrollable_frame)
        mode_frame.grid(row=1, column=1, sticky=tk.W, pady=3)
        ttk.Radiobutton(mode_frame, text="Automático", variable=self.intermediate_mode,
                       value="automatic", command=self.on_intermediate_mode_changed).pack(side=tk.LEFT, padx=(0, 10))
        ttk.Radiobutton(mode_frame, text="Manual", variable=self.intermediate_mode,
                       value="manual", command=self.on_intermediate_mode_changed).pack(side=tk.LEFT)

        # Campo para número de puntos intermedios (automático)
        self.auto_points_label = ttk.Label(scrollable_frame, text="Puntos Intermedios:")
        self.auto_points_label.grid(row=2, column=0, sticky=tk.W, pady=3)

        self.auto_points_spinbox = ttk.Spinbox(scrollable_frame, from_=1, to=100, increment=1,
                                             textvariable=self.num_puntos_intermedios, width=10)
        self.auto_points_spinbox.grid(row=2, column=1, pady=3)

        # Campo para puntos personalizados (manual)
        self.manual_points_label = ttk.Label(scrollable_frame, text="Puntos Personalizados:")
        self.manual_points_label.grid(row=2, column=0, sticky=tk.W, pady=3)

        self.manual_points_entry = ttk.Entry(scrollable_frame, textvariable=self.custom_points_text, width=50)
        self.manual_points_entry.grid(row=2, column=1, pady=3, sticky=tk.W)

        # Información de ayuda
        help_text = "Formato: [0, 1, 2, 3, 4, 5, 6, 6.5, 6.8]\nLos puntos se aplican tanto para subida como bajada"
        self.help_label = ttk.Label(scrollable_frame, text=help_text, font=('Arial', 8),
                                  foreground='gray')
        self.help_label.grid(row=3, column=0, columnspan=2, sticky=tk.W, pady=(0, 10))

        # Opción para habilitar tiempo de estabilización
        self.enable_stability_checkbutton = ttk.Checkbutton(scrollable_frame, text="Habilitar Tiempo de Estabilización",
                       variable=self.enable_stability, command=self.on_stability_option_changed)
        self.enable_stability_checkbutton.grid(row=4, column=0, columnspan=2, sticky=tk.W, pady=3)

        self.stability_time_label = ttk.Label(scrollable_frame, text="Tiempo de Estabilización (segundos):")
        self.stability_time_label.grid(row=5, column=0, sticky=tk.W, pady=3)
        self.stability_time_spinbox = ttk.Spinbox(scrollable_frame, from_=0, to=300, increment=1,
                   textvariable=self.stability_time, width=10)
        self.stability_time_spinbox.grid(row=5, column=1, pady=3)

        # # Configurar parámetros
        self.setpoint_inicial_label = ttk.Label(scrollable_frame, text="Setpoint Inicial (0.0-7.0):")
        self.setpoint_inicial_label.grid(row=6, column=0, sticky=tk.W, pady=3)
        self.setpoint_inicial_spinbox = ttk.Spinbox(scrollable_frame, from_=0.0, to=7.0, increment=0.1,
                   textvariable=self.setpoint_inicial, width=10)
        self.setpoint_inicial_spinbox.grid(row=6, column=1, pady=3)

        self.setpoint_final_label = ttk.Label(scrollable_frame, text="Setpoint Final (0.0-7.0):")
        self.setpoint_final_label.grid(row=7, column=0, sticky=tk.W, pady=3)
        self.setpoint_final_spinbox = ttk.Spinbox(scrollable_frame, from_=0.0, to=7.0, increment=0.1,
                   textvariable=self.setpoint_final, width=10)
        self.setpoint_final_spinbox.grid(row=7, column=1, pady=3)

        ttk.Label(scrollable_frame, text="Intervalo (segundos):").grid(row=8, column=0, sticky=tk.W, pady=3)
        self.setpoint_intervalo_spinbox = ttk.Spinbox(scrollable_frame, from_=1, to=3600, increment=1,
                   textvariable=self.setpoint_intervalo, width=10)
        self.setpoint_intervalo_spinbox.grid(row=8, column=1, pady=3)

        ttk.Label(scrollable_frame, text="Número de Ciclos:").grid(row=9, column=0, sticky=tk.W, pady=3)
        self.num_ciclos_spinbox = ttk.Spinbox(scrollable_frame, from_=1, to=100, increment=1,
                   textvariable=self.num_ciclos, width=10)
        self.num_ciclos_spinbox.grid(row=9, column=1, pady=3)

        # Configurar visibilidad inicial
        self.on_intermediate_mode_changed()
        self.on_stability_option_changed()

        # Frame para la figura de la rutina - tamaño mejorado
        routine_frame = ttk.LabelFrame(scrollable_frame, text="📈 Vista Previa de la Rutina",
                                      style='Section.TLabelframe', padding=5)
        routine_frame.grid(row=0, column=0, columnspan=2, sticky=tk.EW, pady=10)

        # Crear figura para mostrar la rutina - tamaño aumentado
        self.routine_fig = plt.Figure(figsize=(8, 4), dpi=100)  # Más grande y mejor DPI
        self.routine_ax = self.routine_fig.add_subplot(111)
        self.routine_canvas = FigureCanvasTkAgg(self.routine_fig, master=routine_frame)
        self.routine_canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)

        # Configurar márgenes de la figura para mejor uso del espacio
        self.routine_fig.subplots_adjust(left=0.08, right=0.95, top=0.9, bottom=0.15)

        # Configurar eventos para actualizar la vista previa
        self.setpoint_inicial.trace_add("write", lambda *args: self.update_routine_preview())
        self.setpoint_final.trace_add("write", lambda *args: self.update_routine_preview())
        self.setpoint_intervalo.trace_add("write", lambda *args: self.update_routine_preview())
        self.num_ciclos.trace_add("write", lambda *args: self.update_routine_preview())
        self.stability_time.trace_add("write", lambda *args: self.update_routine_preview())

        # Eventos adicionales para modo de puntos intermedios
        self.intermediate_mode.trace_add("write", lambda *args: self.update_routine_preview())
        self.num_puntos_intermedios.trace_add("write", lambda *args: self.update_routine_preview())
        self.custom_points_text.trace_add("write", lambda *args: self.update_routine_preview())
        self.enable_stability.trace_add("write", lambda *args: self.update_routine_preview())

        # Actualizar configuración global cuando cambian los parámetros de puntos intermedios
        self.intermediate_mode.trace_add("write", lambda *args: self.update_global_config())
        self.custom_points_text.trace_add("write", lambda *args: self.update_global_config())

        # Actualizar configuración global cuando cambian los puertos seriales
        self.alicat_port.trace_add("write", lambda *args: self.update_global_config())
        self.tiva_port.trace_add("write", lambda *args: self.update_global_config())

        # Generar la vista previa inicial
        self.update_routine_preview()

        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        # === SECCIÓN DE PUERTOS (derecha) ===
        ports_section = ttk.LabelFrame(right_frame, text="🔌 Configuración de Puertos",
                                      style='Section.TLabelframe', padding=15)
        ports_section.pack(fill=tk.X, pady=(0, 15))

        # Alicat
        alicat_frame = ttk.LabelFrame(ports_section, text="Alicat Controller", padding=8)
        alicat_frame.pack(fill=tk.X, pady=(0, 8))

        ttk.Label(alicat_frame, text="Puerto COM:").grid(row=0, column=0, sticky=tk.W, pady=2)
        self.alicat_combo = ttk.Combobox(alicat_frame, textvariable=self.alicat_port, state="readonly", width=12)
        self.alicat_combo.grid(row=0, column=1, pady=2, sticky=tk.EW, padx=(5,0))
        ttk.Button(alicat_frame, text="🔍 Probar", command=self.test_alicat_connection, width=8).grid(row=0, column=2, padx=(8,0))
        ttk.Button(alicat_frame, text="⚙️ Config", command=self.configure_alicat_serial, width=8).grid(row=0, column=3, padx=(4,0))

        # TIVA
        tiva_frame = ttk.LabelFrame(ports_section, text="TIVA Controller", padding=8)
        tiva_frame.pack(fill=tk.X, pady=(0, 8))

        ttk.Label(tiva_frame, text="Puerto COM:").grid(row=0, column=0, sticky=tk.W, pady=2)
        self.tiva_combo = ttk.Combobox(tiva_frame, textvariable=self.tiva_port, state="readonly", width=12)
        self.tiva_combo.grid(row=0, column=1, pady=2, sticky=tk.EW, padx=(5,0))
        ttk.Button(tiva_frame, text="🔍 Probar", command=self.test_tiva_connection, width=8).grid(row=0, column=2, padx=(8,0))
        ttk.Button(tiva_frame, text="⚙️ Config", command=self.configure_tiva_serial, width=8).grid(row=0, column=3, padx=(4,0))

        # Keithley
        keithley_frame = ttk.LabelFrame(ports_section, text="Keithley Multimeter", padding=8)
        keithley_frame.pack(fill=tk.X, pady=(0, 8))

        ttk.Label(keithley_frame, text="Recurso VISA:").grid(row=0, column=0, sticky=tk.W, pady=2)
        self.keithley_combo = ttk.Combobox(keithley_frame, textvariable=self.keithley_resource, state="readonly", width=12)
        self.keithley_combo.grid(row=0, column=1, pady=2, sticky=tk.EW, padx=(5,0))
        ttk.Button(keithley_frame, text="🔍 Escanear", command=self.scan_keithley_devices, width=10).grid(row=0, column=2, padx=(8,0))
        ttk.Button(keithley_frame, text="🔍 Probar", command=self.test_keithley_connection, width=8).grid(row=0, column=3, padx=(8,0), pady=(5,0))

        ttk.Label(keithley_frame, text="(Opcional)", font=("Arial", 8)).grid(row=1, column=0, columnspan=2, sticky=tk.W)

        ttk.Button(ports_section, text="🔄 Escanear Todos los Puertos", command=self.scan_serial_ports).pack(pady=(5,0))

        # === SECCIÓN DE LOG (derecha) ===
        log_section = ttk.LabelFrame(right_frame, text="📋 Registro de Actividad",
                                    style='Section.TLabelframe', padding=15)
        log_section.pack(fill=tk.BOTH, expand=True)

        # Crear notebook interno para log y puertos
        inner_notebook = ttk.Notebook(log_section)
        inner_notebook.pack(fill=tk.BOTH, expand=True)

        # Pestaña de Log
        log_frame = ttk.Frame(inner_notebook)
        inner_notebook.add(log_frame, text="📝 Log")

        self.log_text = tk.Text(log_frame, height=12, wrap=tk.WORD, bg='#f8f9fa', font=('Consolas', 9))
        log_scrollbar = ttk.Scrollbar(log_frame, orient=tk.VERTICAL, command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=log_scrollbar.set)

        self.log_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        log_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        # Configurar logging para redirigir logs de acquisition_instruments al Text widget
        logger = logging.getLogger('acquisition_instruments')
        logger.setLevel(logging.INFO)
        handler = self.TextHandler(self.log_text)
        handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
        logger.addHandler(handler)

        # Pestaña de Puertos Disponibles
        ports_info_frame = ttk.Frame(inner_notebook)
        inner_notebook.add(ports_info_frame, text="🔌 Puertos")

        self.ports_text = tk.Text(ports_info_frame, height=12, wrap=tk.WORD, bg='#f8f9fa', font=('Consolas', 9))
        ports_scrollbar = ttk.Scrollbar(ports_info_frame, orient=tk.VERTICAL, command=self.ports_text.yview)
        self.ports_text.configure(yscrollcommand=ports_scrollbar.set)

        self.ports_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        ports_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        return page

    def on_stability_option_changed(self):
        """Manejar cambio en la opción de tiempo de estabilización"""
        if self.enable_stability.get():
            self.stability_time_label.grid()
            self.stability_time_spinbox.grid()
        else:
            self.stability_time_label.grid_remove()
            self.stability_time_spinbox.grid_remove()

        # Actualizar configuración global cuando cambia la opción
        self.update_global_config()

    def on_intermediate_mode_changed(self):
        """Manejar cambio de modo de puntos intermedios"""
        mode = self.intermediate_mode.get()

        if mode == "automatic":
            # Mostrar campo automático, ocultar manual
            self.auto_points_label.grid()
            self.auto_points_spinbox.grid()
            self.setpoint_inicial_label.grid()
            self.setpoint_inicial_spinbox.grid()
            self.setpoint_final_label.grid()
            self.setpoint_final_spinbox.grid()
            self.manual_points_label.grid_remove()
            self.manual_points_entry.grid_remove()
            self.help_label.grid_remove()
        else:  # manual
            # Ocultar campo automático, mostrar manual
            self.auto_points_label.grid_remove()
            self.auto_points_spinbox.grid_remove()
            self.setpoint_inicial_label.grid_remove()
            self.setpoint_inicial_spinbox.grid_remove()
            self.setpoint_final_label.grid_remove()
            self.setpoint_final_spinbox.grid_remove()
            self.manual_points_label.grid()
            self.manual_points_entry.grid()
            self.help_label.grid()

        # Actualizar configuración global cuando cambia el modo
        self.update_global_config()

    def create_calibration_page(self):
        """Crear página de calibración PID"""
        page = ttk.Frame(self.content_main, style='Content.TFrame')

        # Layout principal en dos columnas
        page.columnconfigure(0, weight=3)  # Columna izquierda: 3 partes
        page.columnconfigure(1, weight=1)  # Columna derecha: 1 parte
        page.rowconfigure(0, weight=1)     # Fila superior (contenido principal)
        page.rowconfigure(1, weight=1)     # Fila inferior (log)

        left_frame = ttk.Frame(page)
        left_frame.grid(row=0, column=0, sticky=tk.NSEW, padx=(0, 10))

        right_frame = ttk.Frame(page)
        right_frame.grid(row=0, column=1, sticky=tk.NSEW, padx=(10, 0))

        # === SECCIÓN IZQUIERDA: CONFIGURACIÓN PID ===

        # Título
        title_label = ttk.Label(left_frame, text="🔧 Calibración de Parámetros PID",
                               font=("Arial", 16, "bold"), foreground='#2c3e50')
        title_label.pack(pady=(20, 15))

        # Modo de control LCA
        lca_frame = ttk.LabelFrame(left_frame, text="🎛️ Modo de Control LCA",
                                  style='Section.TLabelframe', padding=15)
        lca_frame.pack(fill=tk.X, pady=(0, 15))

        ttk.Label(lca_frame, text="Modo LCA:").grid(row=0, column=0, sticky=tk.W, pady=5)
        self.lca_combo = ttk.Combobox(lca_frame, textvariable=self.lca_mode,
                                     values=["PD/PDF", "PD2I"], state="readonly", width=15)
        self.lca_combo.grid(row=0, column=1, sticky=tk.W, pady=5, padx=(10, 0))
        self.lca_combo.bind('<<ComboboxSelected>>', self.on_lca_mode_changed)

        ttk.Button(lca_frame, text="📥 Consultar Modo", command=self.get_lca_mode).grid(row=0, column=2, padx=(10, 0))
        ttk.Button(lca_frame, text="📤 Establecer Modo", command=self.set_lca_mode).grid(row=0, column=3, padx=(5, 0))

        # Ganancias PID
        gains_frame = ttk.LabelFrame(left_frame, text="⚙️ Ganancias PID",
                                    style='Section.TLabelframe', padding=15)
        gains_frame.pack(fill=tk.X, pady=(0, 15))

        # P Gain
        ttk.Label(gains_frame, text="P Gain:").grid(row=0, column=0, sticky=tk.W, pady=3)
        self.p_gain_spinbox = ttk.Spinbox(gains_frame, from_=0.0, to=100.0, increment=0.1,
                                         textvariable=self.pid_p_gain, width=10)
        self.p_gain_spinbox.grid(row=0, column=1, pady=3, padx=(10, 0))

        # I Gain (solo visible en PD2I)
        self.i_gain_label = ttk.Label(gains_frame, text="I Gain:")
        self.i_gain_label.grid(row=1, column=0, sticky=tk.W, pady=3)
        self.i_gain_spinbox = ttk.Spinbox(gains_frame, from_=0.0, to=100.0, increment=0.1,
                                         textvariable=self.pid_i_gain, width=10)
        self.i_gain_spinbox.grid(row=1, column=1, pady=3, padx=(10, 0))

        # D Gain
        ttk.Label(gains_frame, text="D Gain:").grid(row=2, column=0, sticky=tk.W, pady=3)
        self.d_gain_spinbox = ttk.Spinbox(gains_frame, from_=0.0, to=100.0, increment=0.1,
                                         textvariable=self.pid_d_gain, width=10)
        self.d_gain_spinbox.grid(row=2, column=1, pady=3, padx=(10, 0))

        # Botones para consultar/establecer ganancias
        buttons_frame = ttk.Frame(gains_frame)
        buttons_frame.grid(row=3, column=0, columnspan=2, pady=(10, 0))

        ttk.Button(buttons_frame, text="📥 Consultar Ganancias", command=self.get_pid_gains).grid(row=0, column=0, padx=(0, 5))
        ttk.Button(buttons_frame, text="📤 Establecer Ganancias", command=self.set_pid_gains).grid(row=0, column=1)

        # === SECCIÓN DERECHA: CONTROL DE CALIBRACIÓN ===

        # Parámetros de calibración
        calib_params_frame = ttk.LabelFrame(right_frame, text="🎯 Parámetros de Calibración",
                                           style='Section.TLabelframe', padding=15)
        calib_params_frame.pack(fill=tk.X, pady=(20, 15))

        ttk.Label(calib_params_frame, text="Setpoint de Calibración (0.0-7.0):").grid(row=0, column=0, sticky=tk.W, pady=3)
        ttk.Spinbox(calib_params_frame, from_=0.0, to=7.0, increment=0.1,
                   textvariable=self.calib_setpoint, width=10).grid(row=0, column=1, pady=3, padx=(10, 0))

        ttk.Label(calib_params_frame, text="Duración (segundos):").grid(row=1, column=0, sticky=tk.W, pady=3)
        ttk.Spinbox(calib_params_frame, from_=10, to=3600, increment=10,
                   textvariable=self.calib_duration, width=10).grid(row=1, column=1, pady=3, padx=(10, 0))

        # Botones de control de calibración
        calib_control_frame = ttk.LabelFrame(right_frame, text="🎮 Control de Calibración",
                                            style='Section.TLabelframe', padding=15)
        calib_control_frame.pack(fill=tk.X, pady=(0, 15))

        # Estado de calibración
        status_frame = ttk.Frame(calib_control_frame)
        status_frame.pack(fill=tk.X, pady=(0, 10))

        ttk.Label(status_frame, text="Estado:", font=('Arial', 10, 'bold')).grid(row=0, column=0, sticky=tk.W)
        self.calib_status_label = ttk.Label(status_frame, text="Listo", foreground='#2ecc71')
        self.calib_status_label.grid(row=0, column=1, sticky=tk.W, padx=(10, 0))

        # Botones de control
        control_buttons_frame = ttk.Frame(calib_control_frame)
        control_buttons_frame.pack(pady=(5, 0))

        self.btn_start_calib = ttk.Button(control_buttons_frame, text="▶️ Iniciar Calibración",
                                         command=self.start_calibration, width=18)
        self.btn_start_calib.grid(row=0, column=0, padx=5, pady=5)

        self.btn_stop_calib = ttk.Button(control_buttons_frame, text="⏹️ Detener Calibración",
                                        command=self.stop_calibration,
                                        state=tk.DISABLED, width=18)
        self.btn_stop_calib.grid(row=0, column=1, padx=5, pady=5)

        # === LOG DE CALIBRACIÓN (abajo de ambas columnas) ===

        # Frame para el log que abarca ambas columnas
        log_container = ttk.Frame(page)
        log_container.grid(row=1, column=0, columnspan=2, sticky=tk.NSEW, padx=20, pady=(10, 20))

        log_frame = ttk.LabelFrame(log_container, text="📋 Registro de Calibración",
                                  style='Section.TLabelframe', padding=15)
        log_frame.pack(fill=tk.BOTH, expand=True)

        # Área de texto para el log
        self.calib_text = tk.Text(log_frame, height=15, wrap=tk.WORD, bg='#f8f9fa', font=('Consolas', 9))
        calib_scrollbar = ttk.Scrollbar(log_frame, orient=tk.VERTICAL, command=self.calib_text.yview)
        self.calib_text.configure(yscrollcommand=calib_scrollbar.set)

        self.calib_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        calib_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        # Configurar scrollbar con mouse wheel
        def _on_mousewheel_calib(event):
            self.calib_text.yview_scroll(int(-1*(event.delta/120)), "units")

        self.calib_text.bind("<MouseWheel>", _on_mousewheel_calib)

        # Inicializar visibilidad de campos
        self.update_gain_fields_visibility()

        return page

    def create_visualization_page(self):
        """Crear página de visualización de datos"""
        page = ttk.Frame(self.content_main, style='Content.TFrame')

        # Controles superiores
        control_frame = ttk.Frame(page, style='Content.TFrame')
        control_frame.pack(fill=tk.X, padx=20, pady=(20, 10))

        # Selector de archivo
        file_frame = ttk.LabelFrame(control_frame, text="📁 Selección de Archivo",
                                   style='Section.TLabelframe', padding=10)
        file_frame.pack(fill=tk.X, pady=(0, 10))

        ttk.Label(file_frame, text="Archivo CSV:").grid(row=0, column=0, sticky=tk.W, pady=2)
        ttk.Entry(file_frame, textvariable=self.current_csv_file, width=50).grid(row=0, column=1, sticky=tk.EW, pady=2, padx=(10, 10))
        ttk.Button(file_frame, text="📂 Seleccionar...", command=self.select_csv_file).grid(row=0, column=2)

        # Botones de acción
        action_frame = ttk.Frame(control_frame)
        action_frame.pack(fill=tk.X)

        ttk.Button(action_frame, text="📥 Cargar Datos", command=self.load_csv_data).grid(row=0, column=0, padx=5, pady=5)
        ttk.Button(action_frame, text="📊 Generar Gráficas", command=self.generate_plots).grid(row=0, column=1, padx=5, pady=5)
        ttk.Button(action_frame, text="🧹 Limpiar", command=self.clear_plots).grid(row=0, column=2, padx=5, pady=5)

        # Área de visualización - mejor organización
        viz_container = ttk.Frame(page, style='Content.TFrame')
        viz_container.pack(fill=tk.BOTH, expand=True, padx=20, pady=(10, 20))

        # Panel de control lateral (opcional para filtros/búsqueda)
        control_panel = ttk.Frame(viz_container, style='Content.TFrame', width=200)
        control_panel.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 10))
        control_panel.pack_propagate(False)

        # Área principal de gráficos
        self.viz_plot_frame = ttk.Frame(viz_container, style='Content.TFrame')
        self.viz_plot_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)

        return page

    def create_analysis_page(self):
        """Crear página de análisis estadístico avanzado con pestañas individuales"""
        page = ttk.Frame(self.content_main, style='Content.TFrame')

        # Controles superiores - Combinar selección de archivo y controles de análisis
        control_frame = ttk.Frame(page, style='Content.TFrame')
        control_frame.pack(fill=tk.X, padx=20, pady=(0, 10))

        # Controles de análisis
        analysis_control_frame = ttk.LabelFrame(control_frame, text="🎛️ Controles de Análisis",
                                              style='Section.TLabelframe', padding=15)
        analysis_control_frame.pack(fill=tk.X, pady=(0, 10))

        # Selector de tipo de análisis
        ttk.Label(analysis_control_frame, text="Tipo de Análisis:",
                 font=('Arial', 10, 'bold')).grid(row=0, column=0, sticky=tk.W, pady=5)

        self.analysis_type = tk.StringVar(value="correlation")
        analysis_types = [
            ("correlation", "📊 Análisis de Correlación"),
            ("histogram", "📈 Análisis de Histogramas"),
            ("spectrum", "🌊 Análisis Espectral"),
            ("trend", "📈 Análisis de Tendencias"),
            ("snr", "📡 Análisis SNR (Raw)"),
            ("histeresis", "🔄 Análisis de Histéresis"),
            ("cycle_average", "🔁 Análisis de Ciclos Promedio"),
            ("whitestone_bridge", "🌉 Análisis Puente Wheatstone"),
            ("presion", "💨 Análisis de Presión"),
            ("estadisticas", "📊 Estadísticas Descriptivas")
        ]

        self.analysis_combo = ttk.Combobox(analysis_control_frame, textvariable=self.analysis_type,
                                          values=[code for code, name in analysis_types],
                                          state="readonly", width=25)
        self.analysis_combo.grid(row=0, column=1, sticky=tk.W, pady=5, padx=(10, 0))

        # Mostrar nombre descriptivo
        self.analysis_name_label = ttk.Label(analysis_control_frame, text="📊 Análisis de Correlación",
                                           font=('Arial', 10))
        self.analysis_name_label.grid(row=0, column=2, sticky=tk.W, pady=5, padx=(20, 0))

        # Configurar cambio de nombre descriptivo
        def update_analysis_name(*args):
            for code, name in analysis_types:
                if code == self.analysis_type.get():
                    self.analysis_name_label.config(text=name)
                    break

        self.analysis_type.trace_add("write", update_analysis_name)
        self.analysis_type.trace_add("write", lambda *args: self.update_analysis_controls())

        # Controles específicos por análisis
        self.analysis_controls_frame = ttk.Frame(analysis_control_frame)
        self.analysis_controls_frame.grid(row=0, column=3, columnspan=3, sticky=tk.EW, pady=(0, 0), padx=(20,0))

        # Botones de acción
        buttons_frame = ttk.Frame(analysis_control_frame)
        buttons_frame.grid(row=0, column=6, columnspan=5, pady=(0, 0), padx=(20, 0))

        # Primera fila: botones principales
        ttk.Button(buttons_frame, text="▶️ Ejecutar Análisis",
                  command=self.run_selected_analysis).grid(row=0, column=0, padx=5, pady=5)
        ttk.Button(buttons_frame, text="🧹 Limpiar Pestaña Actual",
                  command=self.clear_current_analysis_tab).grid(row=0, column=1, padx=5, pady=5)

        # Segunda fila: botones de exportación
        ttk.Button(buttons_frame, text="📄 Exportar CSV",
                  command=lambda: self.export_analysis_data('csv')).grid(row=0, column=2, padx=5, pady=5)
        ttk.Button(buttons_frame, text="📊 Exportar XLSX",
                  command=lambda: self.export_analysis_data('xlsx')).grid(row=0, column=3, padx=5, pady=5)
        ttk.Button(buttons_frame, text="🔧 Exportar JSON",
                  command=lambda: self.export_analysis_data('json')).grid(row=0, column=4, padx=5, pady=5)

        # Área de resultados con notebook para pestañas
        results_container = ttk.Frame(page, style='Content.TFrame')
        results_container.pack(fill=tk.BOTH, expand=True, padx=20, pady=(10, 20))

        # Panel lateral para información
        info_panel = ttk.Frame(results_container, style='Content.TFrame', width=250)
        info_panel.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 10))
        info_panel.pack_propagate(False)

        # Información del análisis
        info_frame = ttk.LabelFrame(info_panel, text="ℹ️ Información del Análisis",
                                   style='Section.TLabelframe', padding=10)
        info_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 10))

        self.analysis_info_text = tk.Text(info_frame, height=15, wrap=tk.WORD,
                                        bg='#f8f9fa', font=('Consolas', 9))
        info_scrollbar = ttk.Scrollbar(info_frame, orient=tk.VERTICAL,
                                      command=self.analysis_info_text.yview)
        self.analysis_info_text.configure(yscrollcommand=info_scrollbar.set)

        self.analysis_info_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        info_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        # Notebook para pestañas de análisis
        self.analysis_notebook = ttk.Notebook(results_container, style='Content.TFrame')
        self.analysis_notebook.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)

        # Crear pestañas para cada tipo de análisis
        self.analysis_tabs = {}
        self.analysis_plot_frames = {}

        for analysis_code, analysis_name in analysis_types:
            # Crear frame para la pestaña
            tab_frame = ttk.Frame(self.analysis_notebook, style='Content.TFrame')

            # Área de gráfica para esta pestaña
            plot_frame = ttk.Frame(tab_frame, style='Content.TFrame')
            plot_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

            # Almacenar referencias
            self.analysis_tabs[analysis_code] = tab_frame
            self.analysis_plot_frames[analysis_code] = plot_frame

            # Agregar pestaña al notebook
            self.analysis_notebook.add(tab_frame, text=analysis_name)

        # Configurar controles específicos iniciales
        self.update_analysis_controls()

        return page

    def create_export_page(self):
        """Crear página de exportación de datos"""
        page = ttk.Frame(self.content_main, style='Content.TFrame')

        # Título
        title_label = ttk.Label(page, text="💾 Exportación de Datos y Resultados",
                               font=("Arial", 16, "bold"), foreground='#2c3e50')
        title_label.pack(pady=20)

        # Controles de exportación
        export_frame = ttk.LabelFrame(page, text="📤 Opciones de Exportación",
                                     style='Section.TLabelframe', padding=15)
        export_frame.pack(fill=tk.X, padx=20, pady=(0, 20))

        ttk.Label(export_frame, text="Funcionalidad de exportación próximamente...",
                 font=('Arial', 10)).pack(pady=20)

        return page

    def switch_content(self, page_id):
        """Cambiar entre páginas de contenido"""
        # Ocultar todas las páginas
        for page in self.content_pages.values():
            page.pack_forget()

        # Actualizar botones del sidebar
        for btn_id, btn in self.nav_buttons.items():
            if btn_id == page_id:
                btn.config(bg='#3498db', fg='white')
            else:
                btn.config(bg='#34495e', fg='white')

        # Mostrar página seleccionada
        if page_id in self.content_pages:
            self.content_pages[page_id].pack(fill=tk.BOTH, expand=True)

            # Actualizar título
            titles = {
                'control': 'Panel de Control de Adquisición',
                'calibration': 'Calibración de Parámetros PID',
                'visualization': 'Visualización de Datos',
                'analysis': 'Análisis Estadístico Avanzado',
                'export': 'Exportación de Datos'
            }
            self.content_title.config(text=titles.get(page_id, 'Panel Principal'))

    def create_status_bar(self):
        """Crear barra de estado mejorada"""
        self.status_frame = ttk.Frame(self.root, relief='sunken', borderwidth=1)
        self.status_frame.pack(fill=tk.X, side=tk.BOTTOM)

        # Información de estado
        self.status_label = ttk.Label(self.status_frame, textvariable=self.status_text)
        self.status_label.pack(side=tk.LEFT, padx=10, pady=2)

        # Separador
        ttk.Separator(self.status_frame, orient='vertical').pack(side=tk.LEFT, fill=tk.Y, padx=5)

        # Información adicional
        self.info_label = ttk.Label(self.status_frame, text="Sistema de Adquisición Integrada v2.0")
        self.info_label.pack(side=tk.RIGHT, padx=10, pady=2)

    def update_routine_preview(self):
        """Actualizar la vista previa de la rutina de adquisición"""
        # Verificar que los elementos de la interfaz estén inicializados
        if not hasattr(self, 'routine_ax') or not hasattr(self, 'routine_canvas'):
            return

        try:
            # Obtener valores actuales de los parámetros
            num_ciclos = self.num_ciclos.get()
            punto_inicio = self.setpoint_inicial.get()
            punto_final = self.setpoint_final.get()
            intervalo = self.setpoint_intervalo.get()
            intermediate_mode = self.intermediate_mode.get()

            # Función ciclo (versión local basada en acquisition_instruments)
            def ciclo(num_ciclos, punto_inicio, punto_final, intermediate_mode):
                setpoints = []

                if intermediate_mode == "automatic":
                    # Modo automático: calcular puntos intermedios uniformemente
                    num_puntos_intermedios = self.num_puntos_intermedios.get()
                    for _ in range(num_ciclos):
                        # Barrido ascendente (incluyendo punto inicial y final)
                        for i in range(num_puntos_intermedios + 1):
                            sp = punto_inicio + (punto_final - punto_inicio) * i / num_puntos_intermedios
                            setpoints.append(round(sp, 3))
                        # Barrido descendente (incluyendo punto final y punto inicial para igual número de puntos)
                        for i in range(num_puntos_intermedios + 1):
                            sp = punto_final - (punto_final - punto_inicio) * i / num_puntos_intermedios
                            setpoints.append(round(sp, 3))
                else:
                    # Modo manual: usar puntos personalizados
                    try:
                        # Parsear el texto de puntos personalizados
                        custom_text = self.custom_points_text.get().strip()
                        if custom_text.startswith('[') and custom_text.endswith(']'):
                            custom_text = custom_text[1:-1]  # Remover corchetes
                        custom_points = [float(x.strip()) for x in custom_text.split(',') if x.strip()]

                        for _ in range(num_ciclos):
                            # Barrido ascendente con puntos personalizados
                            setpoints.extend(custom_points)
                            # Barrido descendente con puntos personalizados (revertidos)
                            setpoints.extend(list(reversed(custom_points)))
                    except (ValueError, IndexError) as e:
                        # En caso de error en el parsing, usar modo automático como fallback
                        self.logger.warning(f"Error parsing custom points: {e}. Using automatic mode.")
                        num_puntos_intermedios = self.num_puntos_intermedios.get()
                        for _ in range(num_ciclos):
                            for i in range(num_puntos_intermedios + 1):
                                sp = punto_inicio + (punto_final - punto_inicio) * i / num_puntos_intermedios
                                setpoints.append(round(sp, 3))
                            for i in range(num_puntos_intermedios + 1):
                                sp = punto_final - (punto_final - punto_inicio) * i / num_puntos_intermedios
                                setpoints.append(round(sp, 3))

                return setpoints

            # Generar lista de setpoints
            setpoints = ciclo(num_ciclos, punto_inicio, punto_final, intermediate_mode)

            if not setpoints:
                return

            # Crear datos para gráfica escalonada (step function)
            tiempo_step = []
            setpoint_step = []
            
            tiempo_actual = 0
            for setpoint in setpoints:
                # Cada setpoint se mantiene constante durante el intervalo
                tiempo_step.extend([tiempo_actual, tiempo_actual + intervalo])
                setpoint_step.extend([setpoint, setpoint])
                tiempo_actual += intervalo

            # Convertir a arrays numpy
            tiempo_step = np.array(tiempo_step)
            setpoint_step = np.array(setpoint_step)

            # Limpiar la figura anterior
            self.routine_ax.clear()

            # Graficar la rutina como función escalonada
            self.routine_ax.plot(tiempo_step, setpoint_step, 'b-', linewidth=2, label='Setpoint')
            
            # Agregar marcadores en los puntos de cambio
            tiempo_marcadores = np.arange(0, len(setpoints) * intervalo, intervalo)
            self.routine_ax.plot(tiempo_marcadores, setpoints, 'ro', markersize=4, label='Puntos de setpoint')

            # Configurar etiquetas y título - mejor tamaño de fuente
            self.routine_ax.set_xlabel('Tiempo (segundos)', fontsize=10, fontweight='bold')
            self.routine_ax.set_ylabel('Setpoint (kPA)', fontsize=10, fontweight='bold')
            self.routine_ax.set_title('Rutina de Adquisición (Función Escalonada)', fontsize=12, fontweight='bold', pad=15)
            self.routine_ax.grid(True, alpha=0.3)
            self.routine_ax.legend(fontsize=9, loc='upper right')

            # Ajustar límites con mejor margen
            self.routine_ax.set_xlim(0, tiempo_step[-1] if tiempo_step.size > 0 else 1)
            y_margin = max((punto_final - punto_inicio) * 0.15, 0.1)  # Mínimo margen de 0.1
            self.routine_ax.set_ylim(punto_inicio - y_margin, punto_final + y_margin)

            # Mejorar ticks
            self.routine_ax.tick_params(axis='both', which='major', labelsize=9)

            # Ajustar límites
            self.routine_ax.set_xlim(0, tiempo_step[-1] if tiempo_step.size > 0 else 1)
            y_margin = (punto_final - punto_inicio) * 0.1
            self.routine_ax.set_ylim(punto_inicio - y_margin, punto_final + y_margin)

            # Agregar información de texto
            if intermediate_mode == "automatic":
                info_text = f"Ciclos: {num_ciclos}\nPuntos intermedios: {self.num_puntos_intermedios.get()}\nModo: Automático\nIntervalo: {intervalo}s\nTotal puntos: {len(setpoints)}"
            else:
                try:
                    custom_text = self.custom_points_text.get().strip()
                    if custom_text.startswith('[') and custom_text.endswith(']'):
                        custom_text = custom_text[1:-1]
                    custom_points = [float(x.strip()) for x in custom_text.split(',') if x.strip()]
                    info_text = f"Ciclos: {num_ciclos}\nPuntos personalizados: {len(custom_points)}\nModo: Manual\nIntervalo: {intervalo}s\nTotal puntos: {len(setpoints)}"
                except:
                    info_text = f"Ciclos: {num_ciclos}\nModo: Manual (Error)\nIntervalo: {intervalo}s\nTotal puntos: {len(setpoints)}"

            self.routine_ax.text(0.02, 0.98, info_text, transform=self.routine_ax.transAxes,
                               verticalalignment='top', fontsize=9, fontweight='bold',
                               bbox=dict(boxstyle='round,pad=0.5', facecolor='wheat', alpha=0.9,
                                       edgecolor='orange', linewidth=1))

            # Redibujar el canvas
            self.routine_canvas.draw()

        except Exception as e:
            # En caso de error, mostrar mensaje simple
            self.routine_ax.clear()
            self.routine_ax.text(0.5, 0.5, f'Error al generar\nvista previa:\n{str(e)}',
                               ha='center', va='center', transform=self.routine_ax.transAxes)
            self.routine_canvas.draw()

    def create_status_bar(self):
        """Crear barra de estado"""
        status_frame = ttk.Frame(self.root, relief=tk.SUNKEN)
        status_frame.pack(fill=tk.X, side=tk.BOTTOM)

        ttk.Label(status_frame, text="Estado:").pack(side=tk.LEFT, padx=5)
        ttk.Label(status_frame, textvariable=self.status_text).pack(side=tk.LEFT, padx=5)

    # Métodos de control de adquisición
    def start_acquisition(self):
        """Iniciar la adquisición de datos"""
        if acquisition_instruments.acquisition_running:
            messagebox.showwarning("Advertencia", "La adquisición ya está en ejecución")
            return

        try:
        # Actualizar configuración global
            self.update_global_config()

            # Recolectar parámetros de setpoint
            params = {
                'setpoint_inicial': self.setpoint_inicial.get(),
                'setpoint_final': self.setpoint_final.get(),
                'setpoint_intervalo': self.setpoint_intervalo.get(),
                'num_puntos_intermedios': self.num_puntos_intermedios.get(),
                'num_ciclos': self.num_ciclos.get(),
                'intermediate_mode': self.intermediate_mode.get(),
                'custom_points_text': self.custom_points_text.get(),
                'stability_time': self.stability_time.get(),
                'enable_stability': self.enable_stability.get()
            }

            # Iniciar adquisición usando la función del módulo
            acquisition_instruments.iniciar_adquisicion(params)

            # Actualizar estado local
            self.acquisition_running = True

            # Actualizar botones
            self.btn_start.config(state=tk.DISABLED)
            self.btn_pause.config(state=tk.NORMAL)
            self.btn_stop.config(state=tk.NORMAL)

            self.status_text.set("Adquisición iniciada")
            self.log_message("Adquisición iniciada")

            # Iniciar monitoreo del estado de adquisición
            self.start_acquisition_monitoring()

        except Exception as e:
            messagebox.showerror("Error", f"Error al iniciar adquisición: {e}")
            self.logger.error(f"Error starting acquisition: {e}")

        except Exception as e:
            messagebox.showerror("Error", f"Error al iniciar adquisición: {e}")
            self.logger.error(f"Error starting acquisition: {e}")

    def pause_resume_acquisition(self):
        """Pausar o reanudar la adquisición"""
        if not self.acquisition_running:
            return

        # Usar la función del módulo acquisition_instruments
        acquisition_instruments.pausar_reanudar_adquisicion()

        if acquisition_instruments.acquisition_paused:
            self.status_text.set("Adquisición pausada")
            self.btn_pause.config(text="Reanudar")
            self.log_message("Adquisición pausada")
        else:
            self.status_text.set("Adquisición en ejecución")
            self.btn_pause.config(text="Pausar")
            self.log_message("Adquisición reanudada")

    def stop_acquisition(self):
        """Detener la adquisición"""
        if not acquisition_instruments.acquisition_running:
            return

        # Detener adquisición usando la función del módulo
        acquisition_instruments.detener_adquisicion()

        # Actualizar estado local
        self.acquisition_running = False

        # Detener monitoreo
        self.monitoring_active = False

        # Actualizar botones
        self.btn_start.config(state=tk.NORMAL)
        self.btn_pause.config(state=tk.DISABLED)
        self.btn_stop.config(state=tk.DISABLED)

        self.status_text.set("Adquisición detenida")
        self.log_message("Adquisición detenida")

    def start_acquisition_monitoring(self):
        """Iniciar monitoreo del estado de adquisición para detectar finalización automática"""
        self.monitoring_active = True
        self.root.after(1000, self.check_acquisition_status)  # Verificar cada segundo

    def check_acquisition_status(self):
        """Verificar si la adquisición terminó automáticamente y actualizar GUI"""
        if not self.monitoring_active:
            return

        # Verificar si la adquisición terminó automáticamente
        if self.acquisition_running and not acquisition_instruments.acquisition_running:
            # La adquisición terminó automáticamente, actualizar estado local
            self.acquisition_running = False
            self.monitoring_active = False

            # Actualizar botones
            self.btn_start.config(state=tk.NORMAL)
            self.btn_pause.config(state=tk.DISABLED)
            self.btn_stop.config(state=tk.DISABLED)

            self.status_text.set("Adquisición completada automáticamente")
            self.log_message("Adquisición completada automáticamente (ciclo de setpoints terminado)")

            # Mostrar mensaje al usuario
            messagebox.showinfo("Adquisición Completada",
                              "La adquisición se completó automáticamente al finalizar el ciclo de setpoints configurado.")

        elif self.monitoring_active:
            # Continuar monitoreo
            self.root.after(1000, self.check_acquisition_status)

    # Métodos de calibración
    def start_calibration(self):
        """Iniciar calibración PID"""
        if self.calibration_running:
            messagebox.showwarning("Advertencia", "La calibración ya está en ejecución")
            return

        # Verificar que los widgets de calibración existen
        if not hasattr(self, 'calib_text') or not hasattr(self, 'calib_status_label'):
            messagebox.showerror("Error", "La interfaz de calibración no está inicializada. Navegue a la pestaña de Calibración primero.")
            return

        setpoint = self.calib_setpoint.get()
        duration = self.calib_duration.get()

        if not (0 <= setpoint <= 7.0):
            messagebox.showerror("Error", "Setpoint debe estar entre 0 y 7.0")
            return

        self.calibration_running = True

        # Actualizar estado de botones
        if hasattr(self, 'btn_start_calib'):
            self.btn_start_calib.config(state=tk.DISABLED)
        if hasattr(self, 'btn_stop_calib'):
            self.btn_stop_calib.config(state=tk.NORMAL)
        if hasattr(self, 'calib_status_label'):
            self.calib_status_label.config(text="Ejecutándose", foreground='#f39c12')

        self.thread_calibration = threading.Thread(target=self.calibration_loop, args=(setpoint, duration), daemon=True)
        self.thread_calibration.start()

        self.calib_text.delete(1.0, tk.END)
        self.calib_text.insert(tk.END, f"Iniciando calibración PID\nSetpoint: {setpoint}\nDuración: {duration}s\n\n")

    def stop_calibration(self):
        """Detener calibración PID"""
        # Verificar que los widgets de calibración existen
        if not hasattr(self, 'calib_text'):
            messagebox.showerror("Error", "La interfaz de calibración no está inicializada.")
            return

        self.calibration_running = False
        if self.thread_calibration and self.thread_calibration.is_alive():
            self.thread_calibration.join(timeout=2.0)

        # Actualizar estado de botones
        if hasattr(self, 'btn_start_calib'):
            self.btn_start_calib.config(state=tk.NORMAL)
        if hasattr(self, 'btn_stop_calib'):
            self.btn_stop_calib.config(state=tk.DISABLED)
        if hasattr(self, 'calib_status_label'):
            self.calib_status_label.config(text="Detenido", foreground='#e74c3c')

        self.calib_text.insert(tk.END, "Calibración detenida\n")

    def calibration_loop(self, setpoint, duration):
        """Loop de calibración PID"""
        try:
            alicat = AlicatController(port=self.alicat_port.get())

            with alicat.connection():
                # Ejecutar calibración
                results = alicat.calibrate_pid(setpoint=setpoint, duration=duration)

                self.calib_text.insert(tk.END, f"Calibración completada exitosamente!\n")
                self.calib_text.insert(tk.END, f"Total de mediciones: {results['total_measurements']}\n")
                self.calib_text.insert(tk.END, f"Precisión promedio: {results.get('average_accuracy', 'N/A'):.2f}\n")
                self.calib_text.insert(tk.END, f"Archivo: {results['output_file']}\n")

        except Exception as e:
            self.calib_text.insert(tk.END, f"Error en calibración: {e}\n")
        finally:
            self.calibration_running = False
            # Actualizar estado de botones en el hilo principal
            self.root.after(0, lambda: self._update_calibration_ui_completed())

    def _update_calibration_ui_completed(self):
        """Actualizar UI cuando la calibración se completa (ejecutado en hilo principal)"""
        if hasattr(self, 'btn_start_calib'):
            self.btn_start_calib.config(state=tk.NORMAL)
        if hasattr(self, 'btn_stop_calib'):
            self.btn_stop_calib.config(state=tk.DISABLED)
        if hasattr(self, 'calib_status_label'):
            self.calib_status_label.config(text="Completado", foreground='#2ecc71')

    def on_lca_mode_changed(self, event=None):
        """Manejar cambio en el modo de Loop Control Algorithm"""
        self.update_gain_fields_visibility()

    def update_gain_fields_visibility(self):
        """Actualizar visibilidad de campos de ganancias según el modo LCA seleccionado"""
        mode = self.lca_mode.get()

        if mode == "PD/PDF":
            # Solo mostrar P y D gains, ocultar I gain
            self.i_gain_label.grid_remove()
            self.i_gain_spinbox.grid_remove()
        elif mode == "PD2I":
            # Mostrar P, D e I gains
            self.i_gain_label.grid()
            self.i_gain_spinbox.grid()

    def get_lca_mode(self):
        """Obtener el modo de Loop Control Algorithm del dispositivo Alicat"""
        try:
            alicat = AlicatController(port=self.alicat_port.get())
            with alicat.connection():
                lca_info = alicat.get_loop_control_algorithm()
                current_mode = lca_info.get('algorithm', 'PD/PDF')
                self.lca_mode.set(current_mode)
                self.update_gain_fields_visibility()

                messagebox.showinfo("Modo LCA Obtenido",
                                  f"Modo actual: {current_mode}")
                self.log_message(f"Modo LCA obtenido: {current_mode}")

        except Exception as e:
            error_msg = f"Error obteniendo modo LCA: {e}"
            messagebox.showerror("Error", error_msg)
            self.logger.error(error_msg)

    def set_lca_mode(self):
        """Cambiar el modo de Loop Control Algorithm del dispositivo Alicat"""
        new_mode = self.lca_mode.get()
        try:
            alicat = AlicatController(port=self.alicat_port.get())
            with alicat.connection():
                alicat.set_loop_control_algorithm(new_mode)

                messagebox.showinfo("Modo LCA Cambiado",
                                  f"Modo cambiado exitosamente a: {new_mode}")
                self.log_message(f"Modo LCA cambiado a: {new_mode}")

        except Exception as e:
            error_msg = f"Error cambiando modo LCA: {e}"
            messagebox.showerror("Error", error_msg)
            self.logger.error(error_msg)

    def get_pid_gains(self):
        """Obtener las ganancias PID del dispositivo Alicat"""
        try:
            alicat = AlicatController(port=self.alicat_port.get())
            with alicat.connection():
                pid_info = alicat.get_pid_gains()

                # Actualizar campos según el modo actual
                mode = self.lca_mode.get()
                if mode == "PD/PDF":
                    self.pid_p_gain.set(pid_info.get('p_gain', 0.0))
                    self.pid_d_gain.set(pid_info.get('d_gain', 0.0))
                    self.pid_i_gain.set(0.0)
                elif mode == "PD2I":
                    self.pid_p_gain.set(pid_info.get('p_gain', 0.0))
                    self.pid_i_gain.set(pid_info.get('i_gain', 0.0))
                    self.pid_d_gain.set(pid_info.get('d_gain', 0.0))

                messagebox.showinfo("Ganancias PID Obtenidas",
                                  f"P Gain: {self.pid_p_gain.get()}\n" +
                                  f"D Gain: {self.pid_d_gain.get()}\n" +
                                  (f"I Gain: {self.pid_i_gain.get()}\n" if mode == "PD2I" else ""))
                self.log_message("Ganancias PID obtenidas exitosamente")

        except Exception as e:
            error_msg = f"Error obteniendo ganancias PID: {e}"
            messagebox.showerror("Error", error_msg)
            self.logger.error(error_msg)

    def set_pid_gains(self):
        """Cambiar las ganancias PID del dispositivo Alicat"""
        try:
            mode = self.lca_mode.get()
            p_gain = self.pid_p_gain.get()
            d_gain = self.pid_d_gain.get()
            i_gain = self.pid_i_gain.get() if mode == "PD2I" else 0.0

            alicat = AlicatController(port=self.alicat_port.get())
            with alicat.connection():
                alicat.set_pid_gains(p_gain=p_gain, i_gain=i_gain, d_gain=d_gain)

                messagebox.showinfo("Ganancias PID Cambiadas",
                                  f"Ganancias cambiadas exitosamente:\n" +
                                  f"P Gain: {p_gain}\n" +
                                  f"D Gain: {d_gain}\n" +
                                  (f"I Gain: {i_gain}\n" if mode == "PD2I" else ""))
                self.log_message(f"Ganancias PID cambiadas - P:{p_gain}, I:{i_gain}, D:{d_gain}")

        except Exception as e:
            error_msg = f"Error cambiando ganancias PID: {e}"
            messagebox.showerror("Error", error_msg)
            self.logger.error(error_msg)

    # Métodos de configuración de puertos
    def scan_serial_ports(self):
        """Escanear puertos seriales disponibles"""
        import serial.tools.list_ports

        ports = serial.tools.list_ports.comports()
        port_list = [port.device for port in ports]

        # Actualizar comboboxes
        self.alicat_combo['values'] = port_list
        self.tiva_combo['values'] = port_list

        # Mostrar información
        self.ports_text.delete(1.0, tk.END)
        self.ports_text.insert(tk.END, f"Puertos seriales encontrados: {len(port_list)}\n\n")

        for port in ports:
            self.ports_text.insert(tk.END, f"{port.device}: {port.description}\n")

        self.log_message(f"Escaneados {len(port_list)} puertos seriales")

    def scan_keithley_devices(self):
        """Escanear dispositivos Keithley disponibles vía VISA"""
        try:
            import pyvisa
            rm = pyvisa.ResourceManager()
            resources = rm.list_resources()

            keithley_resources = [r for r in resources if 'GPIB' in r or 'USB' in r or 'TCPIP' in r]

            self.keithley_combo['values'] = keithley_resources

            if keithley_resources:
                self.keithley_resource.set(keithley_resources[0])  # Seleccionar el primero por defecto

            self.log_message(f"Encontrados {len(keithley_resources)} dispositivos VISA")

        except ImportError:
            messagebox.showerror("Error", "PyVISA no está instalado. Instale con: pip install pyvisa pyvisa-py")
        except Exception as e:
            messagebox.showerror("Error", f"Error escaneando dispositivos VISA: {e}")

    def test_alicat_connection(self):
        """Probar conexión con Alicat"""
        # timeout de 2 segundos para la prueba
        timeout = 2
        currentTime = time.time()
        while time.time() - currentTime < timeout:
            time.sleep(0.1)
            try:
                alicat = AlicatController(port=self.alicat_port.get())
                with alicat.connection():
                    firmware = alicat.get_firmware_version()
                    messagebox.showinfo("Éxito", f"Conexión Alicat exitosa\nFirmware: {firmware}")
            except Exception as e:
                messagebox.showerror("Error", f"Error conectando con Alicat: {e}")
            return
        messagebox.showerror("Error", "Error conectando con Alicat: Timeout de conexión")

    def test_tiva_connection(self):
        """Probar conexión con TIVA"""
        try:
            ser = serial.Serial(port=self.tiva_port.get(), baudrate=115200, timeout=1)
            ser.close()
            messagebox.showinfo("Éxito", "Conexión TIVA exitosa")
        except Exception as e:
            messagebox.showerror("Error", f"Error conectando con TIVA: {e}")

    def test_keithley_connection(self):
        """Probar conexión con Keithley"""
        if not self.keithley_resource.get():
            messagebox.showwarning("Advertencia", "Seleccione un recurso VISA primero")
            return

        try:
            keithley_config = self.get_keithley_config()
            keithley_config['resource_string'] = self.keithley_resource.get()

            acquirer = KeithleyAcquisition(keithley_config, self.logger)
            acquirer._connect_instrument()

            # Probar una lectura
            readings = acquirer.acquire_block(1)
            acquirer._disconnect_instrument()

            messagebox.showinfo("Éxito", f"Conexión Keithley exitosa\nLectura: {readings[0] if readings else 'N/A'}")

        except Exception as e:
            messagebox.showerror("Error", f"Error conectando con Keithley: {e}")

    def configure_alicat_serial(self):
        """Abrir ventana de configuración serial para Alicat"""
        self._open_serial_config_window("Alicat Controller", "alicat")

    def configure_tiva_serial(self):
        """Abrir ventana de configuración serial para TIVA"""
        self._open_serial_config_window("TIVA Controller", "tiva")

    def _open_serial_config_window(self, device_name, device_type):
        """Abrir ventana emergente para configuración de parámetros seriales"""
        config_window = tk.Toplevel(self.root)
        config_window.title(f"Configuración Serial - {device_name}")
        config_window.geometry("400x350")
        config_window.resizable(False, False)
        config_window.transient(self.root)
        config_window.grab_set()

        # Centrar la ventana
        config_window.geometry("+{}+{}".format(
            self.root.winfo_rootx() + 50,
            self.root.winfo_rooty() + 50
        ))

        # Frame principal
        main_frame = ttk.Frame(config_window, padding=20)
        main_frame.pack(fill=tk.BOTH, expand=True)

        # Título
        title_label = ttk.Label(main_frame, text=f"Configuración Serial - {device_name}",
                               font=("Arial", 12, "bold"))
        title_label.pack(pady=(0, 20))

        # Variables para los controles
        baudrate_var = tk.StringVar()
        databits_var = tk.StringVar()
        stopbits_var = tk.StringVar()
        parity_var = tk.StringVar()
        flowcontrol_var = tk.StringVar()

        # Configurar valores por defecto según el dispositivo
        if device_type == "alicat":
            baudrate_var.set("19200")
            databits_var.set("8")
            stopbits_var.set("1")
            parity_var.set("None")
            flowcontrol_var.set("None")
        else:  # tiva
            baudrate_var.set("115200")
            databits_var.set("8")
            stopbits_var.set("1")
            parity_var.set("None")
            flowcontrol_var.set("None")

        # Frame para controles
        controls_frame = ttk.Frame(main_frame)
        controls_frame.pack(fill=tk.X, pady=(0, 20))

        # Baudrate
        ttk.Label(controls_frame, text="Baudrate:").grid(row=0, column=0, sticky=tk.W, pady=5)
        baudrate_combo = ttk.Combobox(controls_frame, textvariable=baudrate_var,
                                    values=["1200", "2400", "4800", "9600", "19200", "38400", "57600", "115200"],
                                    state="readonly", width=15)
        baudrate_combo.grid(row=0, column=1, sticky=tk.W, pady=5, padx=(10, 0))

        # Data Bits
        ttk.Label(controls_frame, text="Data Bits:").grid(row=1, column=0, sticky=tk.W, pady=5)
        databits_combo = ttk.Combobox(controls_frame, textvariable=databits_var,
                                    values=["5", "6", "7", "8"],
                                    state="readonly", width=15)
        databits_combo.grid(row=1, column=1, sticky=tk.W, pady=5, padx=(10, 0))

        # Stop Bits
        ttk.Label(controls_frame, text="Stop Bits:").grid(row=2, column=0, sticky=tk.W, pady=5)
        stopbits_combo = ttk.Combobox(controls_frame, textvariable=stopbits_var,
                                    values=["1", "1.5", "2"],
                                    state="readonly", width=15)
        stopbits_combo.grid(row=2, column=1, sticky=tk.W, pady=5, padx=(10, 0))

        # Parity
        ttk.Label(controls_frame, text="Parity:").grid(row=3, column=0, sticky=tk.W, pady=5)
        parity_combo = ttk.Combobox(controls_frame, textvariable=parity_var,
                                  values=["None", "Even", "Odd", "Mark", "Space"],
                                  state="readonly", width=15)
        parity_combo.grid(row=3, column=1, sticky=tk.W, pady=5, padx=(10, 0))

        # Flow Control
        ttk.Label(controls_frame, text="Flow Control:").grid(row=4, column=0, sticky=tk.W, pady=5)
        flowcontrol_combo = ttk.Combobox(controls_frame, textvariable=flowcontrol_var,
                                       values=["None", "XON/XOFF", "RTS/CTS", "DSR/DTR"],
                                       state="readonly", width=15)
        flowcontrol_combo.grid(row=4, column=1, sticky=tk.W, pady=5, padx=(10, 0))

        # Frame para botones
        buttons_frame = ttk.Frame(main_frame)
        buttons_frame.pack(fill=tk.X, pady=(20, 0))

        def apply_config():
            """Aplicar la configuración seleccionada"""
            try:
                # Convertir valores a constantes de serial
                baudrate = int(baudrate_var.get())
                databits = int(databits_var.get())

                # Convertir stop bits
                stopbits_map = {"1": serial.STOPBITS_ONE, "1.5": serial.STOPBITS_ONE_POINT_FIVE, "2": serial.STOPBITS_TWO}
                stopbits = stopbits_map[stopbits_var.get()]

                # Convertir parity
                parity_map = {"None": serial.PARITY_NONE, "Even": serial.PARITY_EVEN,
                            "Odd": serial.PARITY_ODD, "Mark": serial.PARITY_MARK, "Space": serial.PARITY_SPACE}
                parity = parity_map[parity_var.get()]

                # Almacenar configuración en variables de instancia
                if device_type == "alicat":
                    self.alicat_serial_config = {
                        'baudrate': baudrate,
                        'bytesize': databits,
                        'parity': parity,
                        'stopbits': stopbits,
                        'flowcontrol': flowcontrol_var.get()
                    }
                else:  # tiva
                    self.tiva_serial_config = {
                        'baudrate': baudrate,
                        'bytesize': databits,
                        'parity': parity,
                        'stopbits': stopbits,
                        'flowcontrol': flowcontrol_var.get()
                    }

                # Mostrar configuración aplicada
                config_str = f"Configuración aplicada para {device_name}:\n"
                config_str += f"Baudrate: {baudrate}\n"
                config_str += f"Data Bits: {databits}\n"
                config_str += f"Stop Bits: {stopbits_var.get()}\n"
                config_str += f"Parity: {parity_var.get()}\n"
                config_str += f"Flow Control: {flowcontrol_var.get()}"

                messagebox.showinfo("Configuración Aplicada", config_str)
                self.log_message(f"Configuración serial aplicada para {device_name}: baudrate={baudrate}, databits={databits}")

                # Actualizar configuración global inmediatamente
                self.update_global_config()
                self.log_message(f"Configuración global actualizada para {device_name}")

                config_window.destroy()

            except Exception as e:
                messagebox.showerror("Error", f"Error aplicando configuración: {e}")

        def cancel_config():
            """Cancelar configuración"""
            config_window.destroy()

        # Botones
        ttk.Button(buttons_frame, text="Aplicar", command=apply_config).pack(side=tk.RIGHT, padx=(5, 0))
        ttk.Button(buttons_frame, text="Cancelar", command=cancel_config).pack(side=tk.RIGHT)

    # Métodos auxiliares
    def update_global_config(self):
        """Actualizar configuración global para acquisition_instruments"""
        # Actualizar variables globales
        acquisition_instruments.setpoint_inicial = self.setpoint_inicial.get()
        acquisition_instruments.setpoint_final = self.setpoint_final.get()
        acquisition_instruments.setpoint_intervalo = self.setpoint_intervalo.get()
        acquisition_instruments.num_ciclos = self.num_ciclos.get()
        acquisition_instruments.num_puntos_intermedios = self.num_puntos_intermedios.get()

        # Actualizar puertos seriales
        acquisition_instruments.alicat_port = self.alicat_port.get()
        acquisition_instruments.tiva_port = self.tiva_port.get()

        # Actualizar configuración serial avanzada
        if hasattr(acquisition_instruments, 'alicat_serial_config'):
            acquisition_instruments.alicat_serial_config = self.alicat_serial_config
        if hasattr(acquisition_instruments, 'tiva_serial_config'):
            acquisition_instruments.tiva_serial_config = self.tiva_serial_config

        # Actualizar modo de puntos intermedios
        acquisition_instruments.intermediate_mode = self.intermediate_mode.get()
        acquisition_instruments.custom_points_text = self.custom_points_text.get()

        # Actualizar configuración Keithley
        acquisition_instruments.keithley_config.update(self.get_keithley_config())

    def get_keithley_config(self):
        """Obtener configuración de Keithley"""
        return {
            'experiment_label': self.experiment_label.get(),
            'samples_per_count': self.samples_per_count.get(),
            'nplc_cycles': self.nplc_cycles.get(),
            'infinite_mode': self.infinite_mode.get(),
            'num_blocks': self.num_blocks.get(),
            'no_stats': self.no_stats.get(),
            'output_dir': self.output_dir.get(),
            'quiet': self.quiet.get()
        }

    def log_message(self, message):
        """Agregar mensaje al log"""
        timestamp = time.strftime('%H:%M:%S')
        self.log_text.insert(tk.END, f"[{timestamp}] {message}\n")
        self.log_text.see(tk.END)
        self.logger.info(message)

    # Métodos de visualización
    def select_csv_file(self):
        """Seleccionar archivo CSV para visualización"""
        file_path = filedialog.askopenfilename(
            title="Seleccionar archivo CSV",
            filetypes=[("Archivos CSV", "*.csv"), ("Todos los archivos", "*.*")]
        )
        if file_path:
            self.current_csv_file.set(file_path)

    def load_csv_data(self):
        """Cargar datos del archivo CSV"""
        if not self.current_csv_file.get():
            messagebox.showwarning("Advertencia", "Selecciona un archivo CSV primero")
            return

        try:
            self.csv_data = pd.read_csv(self.current_csv_file.get())
            messagebox.showinfo("Éxito", f"Datos cargados exitosamente\nFilas: {len(self.csv_data)}\nColumnas: {len(self.csv_data.columns)}")
            self.log_message(f"Datos CSV cargados: {len(self.csv_data)} filas, {len(self.csv_data.columns)} columnas")
        except Exception as e:
            messagebox.showerror("Error", f"Error cargando CSV: {e}")
            self.logger.error(f"Error loading CSV: {e}")

    def generate_plots(self):
        """Generar gráficas principales con mejor organización y tamaños adaptativos"""
        if self.csv_data is None:
            messagebox.showwarning("Advertencia", "Carga los datos CSV primero")
            return

        try:
            self.clear_plots()

            # Obtener dimensiones del contenedor para adaptar el tamaño
            container_width = self.viz_plot_frame.winfo_width()
            container_height = self.viz_plot_frame.winfo_height()

            # Si el contenedor aún no tiene tamaño, usar valores por defecto
            if container_width < 100:
                container_width = 800
            if container_height < 100:
                container_height = 600

            # Calcular tamaño óptimo de figura
            dpi = 100
            fig_width = min(container_width / dpi * 0.9, 12)
            fig_height = min(container_height / dpi * 0.85, 10)

            # Crear figura con subplots en columna (2 filas, 1 columna)
            fig, axes = plt.subplots(2, 1, figsize=(fig_width, fig_height), dpi=dpi)
            fig.suptitle('Análisis de Datos de Adquisición', fontsize=14, fontweight='bold')

            # Gráfica 1: Voltajes vs Tiempo - mejorada
            if 'Sample' in self.csv_data.columns:
                # Graficar TIVA voltages
                # TIVA Voltage (V) in another y axis but same plot for better visibility

                if 'TIVA Voltage (V)' in self.csv_data.columns:
                    axes[0].plot(self.csv_data['Sample'], self.csv_data['TIVA Voltage (V)'],
                               'b-', label='TIVA Raw', linewidth=1.5, alpha=0.8)

                # Graficar KEITHLEY voltage si está disponible
                if 'KEITHLEY Voltage (V)' in self.csv_data.columns:
                    axes[0].plot(self.csv_data['Sample'], self.csv_data['KEITHLEY Voltage (V)'],
                               'g-', label='KEITHLEY Voltage', linewidth=2, alpha=0.9)

                axes[0].set_xlabel('Muestras', fontsize=10, fontweight='bold')
                axes[0].set_ylabel('Voltaje (V)', fontsize=10, fontweight='bold')
                axes[0].set_title('Voltajes vs Muestras', fontsize=12, fontweight='bold')
                axes[0].legend(fontsize=9)
                axes[0].grid(True, alpha=0.3)
                axes[0].tick_params(axis='both', which='major', labelsize=9)

            # Gráfica 2: Presión Alicat y Setpoint vs Muestras - mejorada
            if 'Sample' in self.csv_data.columns and 'Alicat Presion (kPA)' in self.csv_data.columns:
                axes[1].plot(self.csv_data['Sample'], self.csv_data['Alicat Presion (kPA)'],
                           'g-', label='Presión Actual', linewidth=1.5, alpha=0.8)
                if 'Alicat Setpoint (kPA)' in self.csv_data.columns:
                    axes[1].plot(self.csv_data['Sample'], self.csv_data['Alicat Setpoint (kPA)'],
                               'orange', label='Setpoint', linewidth=2, alpha=0.9)
                if 'Setpoint Enviado (kPA)' in self.csv_data.columns:
                    axes[1].plot(self.csv_data['Sample'], self.csv_data['Setpoint Enviado (kPA)'],
                               'r--', label='Setpoint Enviado', linewidth=1.5, alpha=0.8)
                axes[1].set_xlabel('Muestras', fontsize=10, fontweight='bold')
                axes[1].set_ylabel('Presión (kPA)', fontsize=10, fontweight='bold')
                axes[1].set_title('Presión Alicat vs Muestras', fontsize=12, fontweight='bold')
                axes[1].legend(fontsize=9)
                axes[1].grid(True, alpha=0.3)
                axes[1].tick_params(axis='both', which='major', labelsize=9)

            plt.tight_layout(h_pad=0.3)

            # Crear canvas y añadir a la interfaz
            canvas = FigureCanvasTkAgg(fig, master=self.viz_plot_frame)
            canvas.draw()
            canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

            # Añadir barra de herramientas de navegación
            from matplotlib.backends.backend_tkagg import NavigationToolbar2Tk
            toolbar = NavigationToolbar2Tk(canvas, self.viz_plot_frame)
            toolbar.update()
            toolbar.pack(side=tk.BOTTOM, fill=tk.X)

            # Guardar referencias
            self.plot_figures.append(fig)
            self.plot_canvases.append(canvas)

            self.log_message("Gráficas principales generadas exitosamente")

        except Exception as e:
            error_msg = f"Error generando gráficas: {str(e)}"
            self.log_message(error_msg)
            messagebox.showerror("Error", error_msg)
            self.logger.error(f"Error generating plots: {e}")

    def plot_correlation_analysis(self):
        """Gráfica de correlación entre variables con análisis estadístico mejorado"""
        # Verificar que tenemos datos numéricos suficientes
        numeric_cols = self.csv_data.select_dtypes(include=[np.number]).columns

        if len(numeric_cols) < 2:
            # Mostrar mensaje si no hay suficientes variables numéricas
            fig, ax = plt.subplots(figsize=(8, 6))
            ax.text(0.5, 0.5, 'Se requieren al menos 2 variables numéricas\npara análisis de correlación',
                   transform=ax.transAxes, ha='center', va='center', fontsize=12,
                   bbox=dict(boxstyle="round,pad=0.3", facecolor="lightcoral", alpha=0.5))
            ax.set_title('Análisis de Correlación - Datos Insuficientes')
            ax.set_xlim(0, 1)
            ax.set_ylim(0, 1)
            ax.axis('off')
        else:
            # Calcular matriz de correlación
            corr_matrix = self.csv_data[numeric_cols].corr()

            # Crear figura con subplots para más información
            fig = plt.figure(figsize=(12, 10))

            # Subplot principal: heatmap de correlación
            ax1 = plt.subplot(2, 2, (1, 3))  # Ocupa filas 1-2, columnas 1-3

            # Crear máscara para la diagonal y valores NaN
            mask = np.triu(np.ones_like(corr_matrix, dtype=bool))
            corr_matrix_masked = corr_matrix.copy()
            corr_matrix_masked[mask] = np.nan

            # Crear heatmap con mejor colormap
            im = ax1.imshow(corr_matrix_masked, cmap='RdYlBu_r', aspect='auto',
                           vmin=-1, vmax=1, interpolation='nearest')

            # Añadir etiquetas con mejor formato
            ax1.set_xticks(range(len(corr_matrix.columns)))
            ax1.set_yticks(range(len(corr_matrix.columns)))
            ax1.set_xticklabels([col.replace(' (', '\n(') for col in corr_matrix.columns],
                               rotation=45, ha='right', fontsize=9)
            ax1.set_yticklabels([col.replace(' (', '\n(') for col in corr_matrix.columns],
                               fontsize=9)

            # Añadir valores en las celdas con formato mejorado
            for i in range(len(corr_matrix.columns)):
                for j in range(len(corr_matrix.columns)):
                    if not mask[i, j]:  # Solo mostrar valores en la parte inferior
                        corr_val = corr_matrix.iloc[i, j]
                        # Usar diferentes colores para valores positivos/negativos
                        color = 'white' if abs(corr_val) > 0.7 else 'black'
                        # Formato: mostrar 2 decimales, con signo
                        text = ax1.text(j, i, f'{corr_val:.2f}',
                                       ha="center", va="center", color=color,
                                       fontsize=8, fontweight='bold' if abs(corr_val) > 0.8 else 'normal')

            ax1.set_title('Matriz de Correlación de Pearson', fontsize=12, fontweight='bold')

            # Añadir colorbar con mejor formato
            cbar = plt.colorbar(im, ax=ax1, shrink=0.8)
            cbar.set_label('Coeficiente de Correlación', rotation=270, labelpad=15)
            cbar.ax.tick_params(labelsize=8)

            # Subplot derecho superior: estadísticas descriptivas
            ax2 = plt.subplot(2, 2, 2)

            # Calcular estadísticas básicas
            stats_data = []
            for col in numeric_cols:
                data = self.csv_data[col].dropna()
                if len(data) > 0:
                    stats_data.append({
                        'Variable': col.replace(' (', '\n('),
                        'Media': data.mean(),
                        'Std': data.std(),
                        'Min': data.min(),
                        'Max': data.max(),
                        'N': len(data)
                    })

            if stats_data:
                stats_df = pd.DataFrame(stats_data)

                # Crear tabla de estadísticas
                ax2.axis('tight')
                ax2.axis('off')

                # Crear tabla con colores alternados
                table = ax2.table(cellText=stats_df.round(3).values,
                                colLabels=stats_df.columns,
                                cellLoc='center',
                                loc='center',
                                colColours=['lightblue']*len(stats_df.columns))

                table.auto_set_font_size(False)
                table.set_fontsize(8)
                table.scale(1, 1.2)

                ax2.set_title('Estadísticas Descriptivas', fontsize=10, fontweight='bold')

            # Subplot derecho inferior: distribución de correlaciones
            ax3 = plt.subplot(2, 2, 4)

            # Extraer correlaciones (excluyendo diagonal)
            corr_values = []
            for i in range(len(corr_matrix.columns)):
                for j in range(i+1, len(corr_matrix.columns)):  # Solo parte superior
                    corr_values.append(corr_matrix.iloc[i, j])

            if corr_values:
                # Histograma de valores de correlación
                n, bins, patches = ax3.hist(corr_values, bins=20, alpha=0.7,
                                          color='skyblue', edgecolor='black')

                # Colorear barras basado en fuerza de correlación
                for patch, corr_val in zip(patches, np.digitize(corr_values, bins[:-1])):
                    if abs(corr_val) > 0.8:
                        patch.set_facecolor('darkred')
                    elif abs(corr_val) > 0.6:
                        patch.set_facecolor('red')
                    elif abs(corr_val) > 0.4:
                        patch.set_facecolor('orange')
                    else:
                        patch.set_facecolor('lightgreen')

                ax3.axvline(x=0, color='black', linestyle='--', alpha=0.5)
                ax3.set_xlabel('Coeficiente de Correlación')
                ax3.set_ylabel('Frecuencia')
                ax3.set_title('Distribución de Correlaciones', fontsize=10, fontweight='bold')
                ax3.grid(True, alpha=0.3)

                # Añadir texto con resumen
                strong_corr = sum(1 for c in corr_values if abs(c) > 0.8)
                moderate_corr = sum(1 for c in corr_values if 0.6 <= abs(c) <= 0.8)
                weak_corr = sum(1 for c in corr_values if 0.3 <= abs(c) < 0.6)

                summary_text = f'Correlaciones Fuertes (>0.8): {strong_corr}\nModeradas (0.6-0.8): {moderate_corr}\nDébiles (0.3-0.6): {weak_corr}'
                ax3.text(0.02, 0.98, summary_text, transform=ax3.transAxes,
                        verticalalignment='top', fontsize=8,
                        bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.8))

            plt.tight_layout(h_pad=0.3)

        # Crear canvas y añadir a la pestaña correspondiente
        plot_frame = self.get_current_analysis_plot_frame()
        if plot_frame:
            canvas = FigureCanvasTkAgg(fig, master=plot_frame)
            canvas.draw()
            canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)

            # Almacenar figuras por tipo de análisis
            figures_list = self.get_analysis_figures_list('correlation')
            figures_list.append(fig)

    def plot_histogram_analysis(self):
        """Histogramas de las variables principales"""
        fig, axes = plt.subplots(2, 2, figsize=(12, 8))
        fig.suptitle('Histogramas de Variables Principales')

        plot_vars = []
        if 'TIVA Voltage (V)' in self.csv_data.columns:
            plot_vars.append(('TIVA Voltage (V)', 'b'))
        if 'Alicat Presion (kPA)' in self.csv_data.columns:
            plot_vars.append(('Alicat Presion (kPA)', 'g'))
        if 'TIVA Temp (C)' in self.csv_data.columns:
            plot_vars.append(('TIVA Temp (C)', 'r'))
        if 'KEITHLEY Voltage (V)' in self.csv_data.columns:
            plot_vars.append(('KEITHLEY Voltage (V)', 'orange'))

        for i, (var, color) in enumerate(plot_vars[:4]):
            ax = axes[i//2, i%2]
            ax.hist(self.csv_data[var].dropna(), bins=50, alpha=0.7, color=color, edgecolor='black')
            ax.set_xlabel(var)
            ax.set_ylabel('Frecuencia')
            ax.set_title(f'Histograma de {var}')
            ax.grid(True, alpha=0.3)

        # plt.tight_layout()

        # Crear canvas y añadir a la pestaña correspondiente
        plot_frame = self.get_current_analysis_plot_frame()
        if plot_frame:
            canvas = FigureCanvasTkAgg(fig, master=plot_frame)
            canvas.draw()
            canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)

            # Almacenar figuras por tipo de análisis
            figures_list = self.get_analysis_figures_list('histogram')
            figures_list.append(fig)

    def plot_spectrum_analysis(self):
        """Análisis espectral avanzado con FFT, PSD y análisis de frecuencias"""
        # Determinar qué señales están disponibles
        available_signals = []
        if 'TIVA Voltage (V)' in self.csv_data.columns:
            available_signals.append(('TIVA Voltage (V)', 'Voltaje TIVA'))
        if 'KEITHLEY Voltage (V)' in self.csv_data.columns:
            available_signals.append(('KEITHLEY Voltage (V)', 'Voltaje KEITHLEY'))
        if 'Alicat Presion (kPA)' in self.csv_data.columns:
            available_signals.append(('Alicat Presion (kPA)', 'Presión Alicat'))

        if len(available_signals) == 0:
            # Mostrar mensaje de no data
            fig, ax = plt.subplots(figsize=(8, 6))
            ax.text(0.5, 0.5, 'No hay datos numéricos disponibles para análisis espectral',
                   transform=ax.transAxes, ha='center', va='center', fontsize=12,
                   bbox=dict(boxstyle="round,pad=0.3", facecolor="lightcoral", alpha=0.5))
            ax.set_title('Análisis Espectral - Datos Insuficientes')
            ax.set_xlim(0, 1)
            ax.set_ylim(0, 1)
            ax.axis('off')
        else:
            # Estimar frecuencia de muestreo si hay columna de tiempo
            if 'Timestamp' in self.csv_data.columns:
                try:
                    # Convertir timestamp a tiempo numérico
                    timestamps = pd.to_datetime(self.csv_data['Timestamp'], errors='coerce')
                    time_diffs = timestamps.diff().dt.total_seconds().dropna()
                    if len(time_diffs) > 0:
                        fs = 1.0 / time_diffs.mean()  # Frecuencia de muestreo
                    else:
                        fs = 1.0  # Valor por defecto
                except:
                    fs = 1.0
            else:
                fs = 1.0  # Valor por defecto

            # Crear figura con layout mejorado
            n_signals = min(len(available_signals), 3)
            fig = plt.figure(figsize=(15, 5*n_signals))

            # Procesar cada señal
            for i, (col_name, title) in enumerate(available_signals[:n_signals]):
                signal = self.csv_data[col_name].dropna().values

                if len(signal) < 10:
                    continue  # Saltar señales muy cortas

                # Remover tendencia lineal
                signal_detrended = signal - np.polyval(np.polyfit(np.arange(len(signal)), signal, 1), np.arange(len(signal)))

                # Aplicar ventana de Hann para reducir leakage
                window = np.hanning(len(signal_detrended))
                signal_windowed = signal_detrended * window

                # Calcular FFT
                fft = np.fft.fft(signal_windowed)
                freq = np.fft.fftfreq(len(signal_windowed), d=1/fs)

                # Calcular PSD usando Welch
                from scipy.signal import welch
                freqs_psd, psd = welch(signal_detrended, fs=fs, nperseg=min(1024, len(signal)//4))

                # Solo frecuencias positivas
                pos_mask = freq > 0
                freq_pos = freq[pos_mask]
                fft_pos = np.abs(fft)[pos_mask]

                # Normalizar FFT
                fft_normalized = fft_pos / len(signal)

                # Crear subplots para cada señal (3 columnas: FFT, PSD, Análisis)
                base_row = i * 3

                # 1. FFT - Magnitud
                ax1 = plt.subplot(n_signals, 3, base_row + 1)
                ax1.plot(freq_pos, fft_normalized, 'b-', linewidth=1.5, alpha=0.8)
                ax1.set_xlabel('Frecuencia (Hz)')
                ax1.set_ylabel('Magnitud Normalizada')
                ax1.set_title(f'FFT - {title}')
                ax1.grid(True, alpha=0.3)
                ax1.set_xlim(0, freq_pos.max())

                # Encontrar picos principales
                from scipy.signal import find_peaks
                peaks, properties = find_peaks(fft_normalized, height=np.max(fft_normalized)*0.1, distance=len(freq_pos)//20)
                if len(peaks) > 0:
                    top_peaks = sorted(zip(peaks, properties['peak_heights']), key=lambda x: x[1], reverse=True)[:3]
                    for peak_idx, height in top_peaks:
                        freq_peak = freq_pos[peak_idx]
                        ax1.plot(freq_peak, height, 'ro', markersize=6)
                        ax1.annotate('.2f', xy=(freq_peak, height),
                                   xytext=(5, 5), textcoords='offset points',
                                   fontsize=8, bbox=dict(boxstyle='round,pad=0.2', facecolor='yellow', alpha=0.8))

                # 2. PSD (Power Spectral Density)
                ax2 = plt.subplot(n_signals, 3, base_row + 2)
                ax2.semilogy(freqs_psd, psd, 'r-', linewidth=1.5, alpha=0.8)
                ax2.set_xlabel('Frecuencia (Hz)')
                ax2.set_ylabel('Densidad Espectral de Potencia')
                ax2.set_title(f'PSD - {title}')
                ax2.grid(True, alpha=0.3)
                ax2.set_xlim(0, freqs_psd.max())

                # 3. Análisis de frecuencia y estadísticas
                ax3 = plt.subplot(n_signals, 3, base_row + 3)
                ax3.axis('off')

                # Calcular estadísticas espectrales
                total_power = np.sum(psd)
                dc_power = psd[0]  # Componente DC
                ac_power = total_power - dc_power

                # Frecuencia dominante
                dominant_freq_idx = np.argmax(psd[1:]) + 1  # Excluir DC
                dominant_freq = freqs_psd[dominant_freq_idx]
                dominant_power = psd[dominant_freq_idx]

                # Ancho de banda efectivo (frecuencia donde se concentra el 95% de la energía)
                cumulative_power = np.cumsum(psd) / total_power
                bandwidth_idx = np.where(cumulative_power >= 0.95)[0]
                if len(bandwidth_idx) > 0:
                    bandwidth = freqs_psd[bandwidth_idx[0]]
                else:
                    bandwidth = freqs_psd[-1]

                # SNR estimado (relación señal-ruido)
                if dominant_power > 0:
                    noise_power = (total_power - dominant_power) / (len(psd) - 1)
                    snr = 10 * np.log10(dominant_power / noise_power) if noise_power > 0 else float('inf')
                else:
                    snr = 0

                # Crear tabla de información
                info_text = ".2f"".2f"".2f"".2f"".1f"".2f"".2f"f"""
                        Análisis Espectral - {title}

                        Frecuencia de Muestreo: {fs:.2f} Hz
                        Puntos de Datos: {len(signal)}
                        Resolución Espectral: {freq_pos[1]-freq_pos[0]:.4f} Hz

                        Potencia Total: {total_power:.2e}
                        Potencia DC: {dc_power:.2e} ({dc_power/total_power*100:.1f}%)
                        Potencia AC: {ac_power:.2e} ({ac_power/total_power*100:.1f}%)

                        Frecuencia Dominante: {dominant_freq:.3f} Hz
                        Potencia Dominante: {dominant_power:.2e}
                        Ancho de Banda (95%): {bandwidth:.3f} Hz
                        SNR Estimado: {snr:.1f} dB
                        """

                ax3.text(0.05, 0.95, info_text, transform=ax3.transAxes,
                        verticalalignment='top', fontsize=9, family='monospace',
                        bbox=dict(boxstyle='round,pad=0.5', facecolor='lightgray', alpha=0.8))

            plt.tight_layout(h_pad=0.3)

        # Crear canvas usando el nuevo sistema de pestañas
        self.create_analysis_canvas(fig, 'spectrum')

    def plot_trend_analysis(self):
        """Análisis avanzado de tendencias con múltiples métodos estadísticos"""
        # Determinar qué señales están disponibles para análisis de tendencias
        available_signals = []
        if 'TIVA Voltage (V)' in self.csv_data.columns:
            available_signals.append(('TIVA Voltage (V)', 'Voltaje TIVA (V)'))
        if 'KEITHLEY Voltage (V)' in self.csv_data.columns:
            available_signals.append(('KEITHLEY Voltage (V)', 'Voltaje KEITHLEY (V)'))
        if 'Alicat Presion (kPA)' in self.csv_data.columns:
            available_signals.append(('Alicat Presion (kPA)', 'Presión Alicat (kPA)'))

        if len(available_signals) == 0 or 'Sample' not in self.csv_data.columns:
            # Mostrar mensaje de no data
            fig, ax = plt.subplots(figsize=(8, 6))
            ax.text(0.5, 0.5, 'No hay datos disponibles para análisis de tendencias',
                   transform=ax.transAxes, ha='center', va='center', fontsize=12,
                   bbox=dict(boxstyle="round,pad=0.3", facecolor="lightcoral", alpha=0.5))
            ax.set_title('Análisis de Tendencias - Datos Insuficientes')
            ax.set_xlim(0, 1)
            ax.set_ylim(0, 1)
            ax.axis('off')
        else:
            # Determinar eje X (tiempo o muestras)
            if 'Timestamp' in self.csv_data.columns:
                try:
                    # Usar tiempo real si está disponible
                    timestamps = pd.to_datetime(self.csv_data['Timestamp'], errors='coerce')
                    x = (timestamps - timestamps.min()).dt.total_seconds()
                    x_label = 'Tiempo (segundos)'
                    time_based = True
                except:
                    x = self.csv_data['Sample']
                    x_label = 'Muestras'
                    time_based = False
            else:
                x = self.csv_data['Sample']
                x_label = 'Muestras'
                time_based = False

            # Crear figura con layout mejorado
            n_signals = min(len(available_signals), 3)
            fig = plt.figure(figsize=(15, 5*n_signals))

            # Procesar cada señal
            for i, (col_name, y_label) in enumerate(available_signals[:n_signals]):
                y = self.csv_data[col_name].dropna()

                # Alinear x con y (eliminar NaN)
                valid_indices = ~self.csv_data[col_name].isna()
                x_valid = x[valid_indices]

                if len(y) < 10:
                    continue  # Saltar señales muy cortas

                # Crear subplots para cada señal (3 columnas: Tendencia, Residuos, Estadísticas)
                base_row = i * 3

                # 1. Análisis de tendencias múltiples
                ax1 = plt.subplot(n_signals, 3, base_row + 1)

                # Datos originales
                ax1.scatter(x_valid, y, alpha=0.6, s=8, color='blue', label='Datos', zorder=1)

                # Regresión lineal
                try:
                    coeffs_linear = np.polyfit(x_valid, y, 1)
                    y_linear = np.polyval(coeffs_linear, x_valid)
                    slope_linear = coeffs_linear[0]
                    intercept_linear = coeffs_linear[1]

                    # Calcular R² para regresión lineal
                    ss_res = np.sum((y - y_linear) ** 2)
                    ss_tot = np.sum((y - np.mean(y)) ** 2)
                    r_squared_linear = 1 - (ss_res / ss_tot) if ss_tot != 0 else 0

                    ax1.plot(x_valid, y_linear, 'r-', linewidth=2, label='.4f', zorder=2)

                except:
                    slope_linear = 0
                    r_squared_linear = 0

                # Regresión polinomial (grado 2) si hay suficientes puntos
                if len(y) > 20:
                    try:
                        coeffs_poly = np.polyfit(x_valid, y, 2)
                        y_poly = np.polyval(coeffs_poly, x_valid)
                        ax1.plot(x_valid, y_poly, 'g--', linewidth=2, label='Tendencia Polinomial', zorder=3)
                    except:
                        pass

                # Tendencia móvil (media móvil)
                if len(y) > 50:
                    window_size = min(50, len(y) // 10)
                    y_moving = y.rolling(window=window_size, center=True).mean()
                    ax1.plot(x_valid, y_moving, 'orange', linewidth=2, label=f'Media Móvil (n={window_size})', zorder=4)

                ax1.set_xlabel(x_label)
                ax1.set_ylabel(y_label)
                ax1.set_title(f'Análisis de Tendencias - {y_label.split(" (")[0]}')
                ax1.legend(fontsize=8)
                ax1.grid(True, alpha=0.3)

                # 2. Análisis de residuos y diagnóstico
                ax2 = plt.subplot(n_signals, 3, base_row + 2)

                if 'slope_linear' in locals() and slope_linear != 0:
                    # Calcular residuos
                    residuals = y - y_linear

                    # Gráfico de residuos vs tiempo
                    ax2.scatter(x_valid, residuals, alpha=0.6, s=8, color='purple')
                    ax2.axhline(y=0, color='red', linestyle='--', alpha=0.7)

                    # Tendencia en residuos (debe ser aleatoria)
                    if len(residuals) > 20:
                        coeffs_resid = np.polyfit(x_valid, residuals, 1)
                        y_resid_trend = np.polyval(coeffs_resid, x_valid)
                        ax2.plot(x_valid, y_resid_trend, 'green', linewidth=1, alpha=0.7, label='Tendencia residual')

                    ax2.set_xlabel(x_label)
                    ax2.set_ylabel('Residuos')
                    ax2.set_title('Análisis de Residuos')
                    ax2.legend(fontsize=8)
                    ax2.grid(True, alpha=0.3)

                    # Estadísticas de residuos
                    std_residuals = np.std(residuals)
                    ax2.text(0.02, 0.98, f'σ = {std_residuals:.2e}', transform=ax2.transAxes,
                            verticalalignment='top', fontsize=8,
                            bbox=dict(boxstyle='round', facecolor='lightyellow', alpha=0.8))
                else:
                    ax2.text(0.5, 0.5, 'No hay tendencia lineal\npara analizar residuos',
                            transform=ax2.transAxes, ha='center', va='center', fontsize=10)
                    ax2.set_title('Análisis de Residuos')

                # 3. Estadísticas y métricas de tendencia
                ax3 = plt.subplot(n_signals, 3, base_row + 3)
                ax3.axis('off')

                # Calcular estadísticas de tendencia
                mean_value = np.mean(y)
                std_value = np.std(y)
                min_value = np.min(y)
                max_value = np.max(y)
                range_value = max_value - min_value

                # Estadísticas de cambio
                if len(y) > 1:
                    total_change = y.iloc[-1] - y.iloc[0]
                    relative_change = (total_change / abs(y.iloc[0])) * 100 if y.iloc[0] != 0 else 0

                    # Velocidad de cambio promedio
                    if time_based and len(x_valid) > 1:
                        time_span = x_valid.iloc[-1] - x_valid.iloc[0]
                        change_rate = total_change / time_span if time_span > 0 else 0
                    else:
                        change_rate = total_change / len(y)
                else:
                    total_change = 0
                    relative_change = 0
                    change_rate = 0

                # Monotonicidad (tendencia general)
                diffs = np.diff(y)
                increasing_ratio = np.sum(diffs > 0) / len(diffs) if len(diffs) > 0 else 0
                if increasing_ratio > 0.6:
                    monotonicity = "Tendencia Ascendente"
                elif increasing_ratio < 0.4:
                    monotonicity = "Tendencia Descendente"
                else:
                    monotonicity = "Tendencia Mixta"

                # Crear tabla de información
                info_text = ".2f"".2f"".2f"".2f"".2f"".2f"".2f"".3f"".1f"".2f"".2f"".2f"".2f"".2f"f"""
                        Estadísticas de Tendencia - {y_label.split(' (')[0]}

                        Estadísticas Básicas:
                        Media: {mean_value:.4f}
                        Desviación Estándar: {std_value:.4f}
                        Mínimo: {min_value:.4f}
                        Máximo: {max_value:.4f}
                        Rango: {range_value:.4f}

                        Análisis de Tendencia:
                        Cambio Total: {total_change:.4f}
                        Cambio Relativo: {relative_change:.1f}%
                        Velocidad de Cambio: {change_rate:.2e} por unidad
                        Monotonicidad: {monotonicity}

                        Regresión Lineal:
                        Pendiente: {slope_linear:.6f}
                        R²: {r_squared_linear:.3f}
                        Significancia: {'Alta' if r_squared_linear > 0.7 else 'Moderada' if r_squared_linear > 0.3 else 'Baja'}
                        """

                ax3.text(0.05, 0.95, info_text, transform=ax3.transAxes,
                        verticalalignment='top', fontsize=8, family='monospace',
                        bbox=dict(boxstyle='round,pad=0.5', facecolor='lightblue', alpha=0.8))

            plt.tight_layout(h_pad=0.3)

        # Crear canvas usando el nuevo sistema de pestañas
        self.create_analysis_canvas(fig, 'trend')

    def plot_snr_analysis(self):
        """Análisis avanzado de Relación Señal-Ruido (SNR) con múltiples perspectivas"""
        # Verificar que tenemos las señales necesarias
        if 'KEITHLEY Voltage (V)' not in self.csv_data.columns:
            fig, ax = plt.subplots(figsize=(8, 6))
            ax.text(0.5, 0.5, 'Se requiere columna KEITHLEY Voltage (V) para análisis SNR',
                   transform=ax.transAxes, ha='center', va='center', fontsize=12,
                   bbox=dict(boxstyle="round,pad=0.3", facecolor="lightcoral", alpha=0.5))
            ax.set_title('Análisis SNR - Datos Insuficientes')
            ax.set_xlim(0, 1)
            ax.set_ylim(0, 1)
            ax.axis('off')
        else:
            signal = self.csv_data['KEITHLEY Voltage (V)'].dropna()

            if len(signal) < 10:
                fig, ax = plt.subplots(figsize=(8, 6))
                ax.text(0.5, 0.5, 'Se requieren al menos 10 muestras para análisis SNR',
                       transform=ax.transAxes, ha='center', va='center', fontsize=12,
                       bbox=dict(boxstyle="round,pad=0.3", facecolor="lightcoral", alpha=0.5))
                ax.set_title('Análisis SNR - Datos Insuficientes')
                ax.set_xlim(0, 1)
                ax.set_ylim(0, 1)
                ax.axis('off')
            else:
                # Crear figura con múltiples paneles de análisis
                fig = plt.figure(figsize=(15, 12))
                fig.suptitle('Análisis Avanzado de Relación Señal-Ruido (SNR)', fontsize=16, fontweight='bold')

                # Panel 1: Señal original y componentes
                ax1 = plt.subplot(3, 3, (1, 2))
                ax1.plot(signal.index, signal.values, 'b-', linewidth=1.5, label='Señal KEITHLEY')
                ax1.set_xlabel('Índice de Muestra')
                ax1.set_ylabel('Voltaje (V)')
                ax1.set_title('Señal Original', fontweight='bold')
                ax1.grid(True, alpha=0.3)
                ax1.legend()

                # Calcular componentes de la señal
                # Tendencia (señal de baja frecuencia)
                from scipy import signal as scipy_signal
                if len(signal) > 50:  # Solo si hay suficientes datos
                    # Filtro pasa bajos para extraer tendencia
                    b, a = scipy_signal.butter(4, 0.1, 'low')
                    trend = scipy_signal.filtfilt(b, a, signal.values)
                    ax1.plot(signal.index, trend, 'r--', linewidth=2, label='Tendencia (LPF)', alpha=0.8)

                    # Componente de ruido (alta frecuencia)
                    noise = signal.values - trend
                    ax1.plot(signal.index, noise + signal.mean(), 'g-', linewidth=1, label='Ruido (HPF)', alpha=0.6)
                    ax1.legend()

                # Panel 2: Histograma y distribución de la señal
                ax2 = plt.subplot(3, 3, 3)
                n, bins, patches = ax2.hist(signal.values, bins=50, alpha=0.7, color='skyblue', edgecolor='black', density=True)

                # Ajustar distribución normal
                from scipy import stats
                mu, std = stats.norm.fit(signal.values)
                xmin, xmax = ax2.get_xlim()
                x = np.linspace(xmin, xmax, 100)
                p = stats.norm.pdf(x, mu, std)
                ax2.plot(x, p, 'r-', linewidth=2, label=f'Normal\nμ={mu:.4f}\nσ={std:.4f}')

                ax2.set_xlabel('Voltaje (V)')
                ax2.set_ylabel('Densidad de Probabilidad')
                ax2.set_title('Distribución de la Señal', fontweight='bold')
                ax2.legend()
                ax2.grid(True, alpha=0.3)

                # Panel 3: Análisis de SNR en el tiempo
                ax3 = plt.subplot(3, 3, (4, 5))

                # Calcular SNR usando diferentes métodos
                snr_methods = {}

                # Método 1: SNR basado en varianza total vs varianza de residuo
                if len(signal) > 50:
                    # Usar filtro para separar señal y ruido
                    b, a = scipy_signal.butter(4, 0.05, 'low')  # Frecuencia de corte baja
                    signal_filtered = scipy_signal.filtfilt(b, a, signal.values)
                    noise_component = signal.values - signal_filtered

                    signal_power = np.var(signal_filtered)
                    noise_power = np.var(noise_component)

                    if noise_power > 0:
                        snr_total = 10 * np.log10(signal_power / noise_power)
                        snr_methods['Filtro Digital'] = snr_total

                # Método 2: SNR usando promedio móvil
                window_size = min(50, len(signal) // 10)
                if window_size > 5:
                    signal_smooth = pd.Series(signal.values).rolling(window=window_size, center=True).mean().dropna()
                    noise_rolling = signal.values[len(signal)-len(signal_smooth):] - signal_smooth.values

                    if len(noise_rolling) > 0:
                        signal_power_roll = np.var(signal_smooth.values)
                        noise_power_roll = np.var(noise_rolling)

                        if noise_power_roll > 0:
                            snr_rolling = 10 * np.log10(signal_power_roll / noise_power_roll)
                            snr_methods['Promedio Móvil'] = snr_rolling

                # Método 3: SNR en bandas de frecuencia
                if len(signal) > 100:
                    # FFT para análisis frecuencial
                    fft = np.fft.fft(signal.values)
                    freqs = np.fft.fftfreq(len(signal))

                    # Bandas de frecuencia
                    pos_freq_mask = freqs > 0
                    freqs_pos = freqs[pos_freq_mask]
                    fft_pos = np.abs(fft[pos_freq_mask])

                    # Banda baja (señal principal)
                    low_freq_mask = freqs_pos < 0.1
                    if np.any(low_freq_mask):
                        signal_band_power = np.sum(fft_pos[low_freq_mask]**2)
                    else:
                        signal_band_power = np.sum(fft_pos[:len(fft_pos)//10]**2)

                    # Banda alta (ruido)
                    high_freq_mask = freqs_pos > 0.3
                    if np.any(high_freq_mask):
                        noise_band_power = np.sum(fft_pos[high_freq_mask]**2)
                    else:
                        noise_band_power = np.sum(fft_pos[-len(fft_pos)//10:]**2)

                    if noise_band_power > 0:
                        snr_freq = 10 * np.log10(signal_band_power / noise_band_power)
                        snr_methods['Análisis Espectral'] = snr_freq

                # Graficar SNR por método
                if snr_methods:
                    methods = list(snr_methods.keys())
                    values = list(snr_methods.values())

                    bars = ax3.bar(methods, values, color=['skyblue', 'lightgreen', 'lightcoral'][:len(methods)], alpha=0.7)
                    ax3.set_ylabel('SNR (dB)')
                    ax3.set_title('SNR por Método de Cálculo', fontweight='bold')
                    ax3.grid(True, alpha=0.3)

                    # Añadir valores sobre las barras
                    for bar, val in zip(bars, values):
                        height = bar.get_height()
                        ax3.text(bar.get_x() + bar.get_width()/2., height + 0.5,
                                '.1f', ha='center', va='bottom', fontweight='bold')

                    # Línea de referencia
                    ax3.axhline(y=20, color='red', linestyle='--', alpha=0.7, label='SNR Bueno (20dB)')
                    ax3.axhline(y=10, color='orange', linestyle='--', alpha=0.7, label='SNR Aceptable (10dB)')
                    ax3.legend()
                else:
                    ax3.text(0.5, 0.5, 'Datos insuficientes para\ncálculo de SNR múltiple',
                           transform=ax3.transAxes, ha='center', va='center', fontsize=10)
                    ax3.set_xlim(0, 1)
                    ax3.set_ylim(0, 1)
                    ax3.axis('off')

                # Panel 4: Espectro de potencia
                ax4 = plt.subplot(3, 3, 6)
                if len(signal) > 100:
                    # Calcular PSD usando Welch
                    from scipy.signal import welch
                    freqs_welch, psd = welch(signal.values, fs=1.0, nperseg=min(256, len(signal)//4))

                    ax4.semilogy(freqs_welch, psd, 'b-', linewidth=1.5)
                    ax4.set_xlabel('Frecuencia Normalizada')
                    ax4.set_ylabel('Densidad de Potencia')
                    ax4.set_title('Espectro de Potencia', fontweight='bold')
                    ax4.grid(True, alpha=0.3)

                    # Marcar bandas
                    ax4.axvspan(0, 0.1, alpha=0.2, color='green', label='Banda Señal')
                    ax4.axvspan(0.3, 0.5, alpha=0.2, color='red', label='Banda Ruido')
                    ax4.legend()
                else:
                    ax4.text(0.5, 0.5, 'Datos insuficientes para\nanálisis espectral',
                           transform=ax4.transAxes, ha='center', va='center', fontsize=10)
                    ax4.set_xlim(0, 1)
                    ax4.set_ylim(0, 1)
                    ax4.axis('off')

                # Panel 5: SNR vs tiempo (ventanas deslizantes)
                ax5 = plt.subplot(3, 3, (7, 8))
                if len(signal) > 100:
                    # Calcular SNR en ventanas deslizantes
                    window_size = max(50, len(signal) // 20)
                    step_size = window_size // 4

                    snr_time_series = []
                    time_indices = []

                    for start in range(0, len(signal) - window_size + 1, step_size):
                        end = start + window_size
                        window_data = signal.values[start:end]

                        # Filtro simple para separar señal y ruido
                        trend_window = pd.Series(window_data).rolling(window=min(20, len(window_data)//5), center=True).mean().dropna()
                        if len(trend_window) > 10:
                            noise_window = window_data[len(window_data)-len(trend_window):] - trend_window.values

                            signal_power_win = np.var(trend_window.values)
                            noise_power_win = np.var(noise_window)

                            if noise_power_win > 0:
                                snr_win = 10 * np.log10(signal_power_win / noise_power_win)
                                snr_time_series.append(snr_win)
                                time_indices.append(start + window_size // 2)

                    if snr_time_series:
                        ax5.plot(time_indices, snr_time_series, 'b-', linewidth=2, marker='o', markersize=3)
                        ax5.set_xlabel('Índice de Muestra')
                        ax5.set_ylabel('SNR (dB)')
                        ax5.set_title('Evolución Temporal del SNR', fontweight='bold')
                        ax5.grid(True, alpha=0.3)

                        # Estadísticas del SNR temporal
                        snr_mean = np.mean(snr_time_series)
                        snr_std = np.std(snr_time_series)
                        ax5.axhline(y=snr_mean, color='red', linestyle='--', alpha=0.7,
                                   label=f'Promedio: {snr_mean:.1f} dB')
                        ax5.axhline(y=snr_mean + snr_std, color='orange', linestyle=':', alpha=0.7,
                                   label=f'+1σ: {(snr_mean + snr_std):.1f} dB')
                        ax5.axhline(y=snr_mean - snr_std, color='orange', linestyle=':', alpha=0.7,
                                   label=f'-1σ: {(snr_mean - snr_std):.1f} dB')
                        ax5.legend()
                    else:
                        ax5.text(0.5, 0.5, 'No se pudo calcular\nSNR temporal',
                               transform=ax5.transAxes, ha='center', va='center', fontsize=10)
                        ax5.set_xlim(0, 1)
                        ax5.set_ylim(0, 1)
                        ax5.axis('off')
                else:
                    ax5.text(0.5, 0.5, 'Datos insuficientes para\nanálisis temporal',
                           transform=ax5.transAxes, ha='center', va='center', fontsize=10)
                    ax5.set_xlim(0, 1)
                    ax5.set_ylim(0, 1)
                    ax5.axis('off')

                # Panel 6: Estadísticas resumen
                ax6 = plt.subplot(3, 3, 9)

                # Calcular estadísticas básicas de la señal
                signal_stats = {
                    'Media': np.mean(signal.values),
                    'Desv. Est.': np.std(signal.values),
                    'Mínimo': np.min(signal.values),
                    'Máximo': np.max(signal.values),
                    'Rango': np.max(signal.values) - np.min(signal.values),
                    'RMS': np.sqrt(np.mean(signal.values**2))
                }

                # SNR promedio (usando el mejor método disponible)
                best_snr = None
                if snr_methods:
                    # Elegir el SNR más conservador (menor valor)
                    best_snr = min(snr_methods.values())

                if best_snr is not None:
                    signal_stats['SNR Promedio'] = best_snr

                # Crear tabla de estadísticas
                ax6.axis('tight')
                ax6.axis('off')

                stat_labels = list(signal_stats.keys())
                stat_values = [f'{v:.4f}' if isinstance(v, (int, float)) else str(v) for v in signal_stats.values()]

                table_data = [[label, value] for label, value in zip(stat_labels, stat_values)]
                table = ax6.table(cellText=table_data,
                                colLabels=['Métrica', 'Valor'],
                                cellLoc='center',
                                loc='center',
                                colColours=['lightblue', 'lightgreen'])

                table.auto_set_font_size(False)
                table.set_fontsize(9)
                table.scale(1, 1.5)

                ax6.set_title('Estadísticas de la Señal', fontsize=11, fontweight='bold')

                plt.tight_layout(h_pad=0.3)

        # Crear canvas usando el nuevo sistema de pestañas
        self.create_analysis_canvas(fig, 'snr')

    def calculate_snr_sliding(self, signal_ref, signal_meas, samples, window_size=20, step=10):
        """Calcula SNR en ventanas deslizantes"""
        snr_values = []
        times = []

        for i in range(0, len(signal_ref) - window_size + 1, step):
            ref_window = signal_ref[i:i+window_size]
            meas_window = signal_meas[i:i+window_size]
            time_window = samples[i:i+window_size]

            noise = np.array(meas_window) - np.array(ref_window)
            var_signal = np.var(ref_window)
            var_noise = np.var(noise)

            if var_noise > 0:
                snr = 10 * np.log10(var_signal / var_noise)
            else:
                snr = 50  # Cap at 50 dB if noise is zero

            snr_values.append(snr)
            times.append(np.mean(time_window))

        return times, snr_values
        """Panel: Matriz de correlación de métricas de ciclo"""
        if len(cycle_data) < 3:
            ax.text(0.5, 0.5, 'Insuficientes ciclos\npara correlación', ha='center', va='center', transform=ax.transAxes)
            ax.set_title('Correlación')
            ax.axis('off')
            return

        # Extraer métricas para correlación
        durations = [c['duration'] for c in cycle_data]
        setpoint_ranges = [c['setpoint_range'] for c in cycle_data]

        if cycle_data[0]['signals']:
            signal_name = list(cycle_data[0]['signals'].keys())[0]
            hysteresis = [c['signals'][signal_name]['hysteresis'] for c in cycle_data]
            efficiencies = [c['signals'][signal_name]['efficiency'] for c in cycle_data]

            # Crear matriz de datos
            data_matrix = np.array([durations, setpoint_ranges, hysteresis, efficiencies]).T
            labels = ['Duración', 'Rango Setpoint', 'Histéresis', 'Eficiencia']

            # Calcular correlación
            corr_matrix = np.corrcoef(data_matrix.T)

            # Crear heatmap
            im = ax.imshow(corr_matrix, cmap='RdYlBu_r', aspect='auto', vmin=-1, vmax=1)

            # Añadir etiquetas
            ax.set_xticks(range(len(labels)))
            ax.set_yticks(range(len(labels)))
            ax.set_xticklabels(labels, rotation=45, ha='right', fontsize=7)
            ax.set_yticklabels(labels, fontsize=7)

            # Añadir valores
            for i in range(len(labels)):
                for j in range(len(labels)):
                    ax.text(j, i, f'{corr_matrix[i, j]:.2f}', ha='center', va='center',
                           fontsize=6, fontweight='bold')

            ax.set_title('Matriz de\nCorrelación', fontsize=9, fontweight='bold')

            # Colorbar
            plt.colorbar(im, ax=ax, shrink=0.8)
        else:
            ax.text(0.5, 0.5, 'Sin métricas\nde señal', ha='center', va='center', transform=ax.transAxes)
            ax.set_title('Correlación')
            ax.axis('off')

    def _plot_box_plots(self, ax, available_vars, var_labels):
        """Panel 3: Box plots comparativos"""
        if not available_vars:
            ax.text(0.5, 0.5, 'Sin datos', ha='center', va='center', transform=ax.transAxes)
            ax.set_title('Box Plots')
            ax.axis('off')
            return

        # Preparar datos para box plot
        plot_data = []
        plot_labels = []

        for i, var in enumerate(available_vars[:4]):  # Máximo 4 variables
            data = self.csv_data[var].dropna()
            if len(data) > 0:
                plot_data.append(data)
                plot_labels.append(var_labels[i][:12])  # Truncar etiquetas

        if plot_data:
            bp = ax.boxplot(plot_data, labels=plot_labels, patch_artist=True,
                          boxprops=dict(facecolor='lightblue', alpha=0.7),
                          medianprops=dict(color='red', linewidth=2),
                          whiskerprops=dict(color='blue', linewidth=1.5),
                          capprops=dict(color='blue', linewidth=1.5))

            ax.set_ylabel('Valor', fontsize=8)
            ax.set_title('Box Plots\nComparativos', fontsize=9, fontweight='bold')
            ax.grid(True, axis='y', alpha=0.3)
            ax.tick_params(labelsize=7)

            # Rotar etiquetas si son largas
            if len(plot_labels) > 2:
                ax.tick_params(axis='x', rotation=45)

    def _plot_data_quality(self, ax, available_vars):
        """Panel 4: Análisis de calidad de datos"""
        if not available_vars:
            ax.text(0.5, 0.5, 'Sin datos', ha='center', va='center', transform=ax.transAxes)
            ax.set_title('Calidad de Datos')
            ax.axis('off')
            return

        quality_metrics = []
        for var in available_vars:
            total_points = len(self.csv_data)
            missing_points = self.csv_data[var].isnull().sum()
            valid_points = total_points - missing_points

            if valid_points > 0:
                # Calcular outliers usando IQR
                data = self.csv_data[var].dropna()
                Q1 = np.percentile(data, 25)
                Q3 = np.percentile(data, 75)
                IQR = Q3 - Q1
                outliers = ((data < (Q1 - 1.5 * IQR)) | (data > (Q3 + 1.5 * IQR))).sum()

                quality_metrics.append({
                    'Variable': var.split('(')[0][:10],
                    'Válidos': f'{valid_points}/{total_points}',
                    'Outliers': outliers,
                    'Completitud': f'{valid_points/total_points*100:.1f}%'
                })

        if quality_metrics:
            df_quality = pd.DataFrame(quality_metrics)
            ax.axis('tight')
            ax.axis('off')

            table = ax.table(cellText=df_quality.values,
                           colLabels=df_quality.columns,
                           cellLoc='center',
                           loc='center',
                           colColours=['lightgreen'] * len(df_quality.columns))

            table.auto_set_font_size(False)
            table.set_fontsize(6)
            table.scale(1, 1.2)

        ax.set_title('Calidad de\nDatos', fontsize=9, fontweight='bold')

    def _plot_trend_analysis(self, ax, var_name):
        """Panel 5: Análisis de tendencias temporales"""
        if not var_name or 'Sample' not in self.csv_data.columns:
            ax.text(0.5, 0.5, 'Sin datos\ntemporales', ha='center', va='center', transform=ax.transAxes)
            ax.set_title('Tendencias')
            ax.axis('off')
            return

        samples = self.csv_data['Sample'].values
        data = self.csv_data[var_name].dropna()

        if len(data) > 10:
            # Tendencia lineal
            from scipy import stats
            slope, intercept, r_value, p_value, std_err = stats.linregress(samples[:len(data)], data)

            ax.scatter(samples[:len(data)], data, alpha=0.6, s=10, color='blue', label='Datos')
            ax.plot(samples[:len(data)],
                   intercept + slope * samples[:len(data)],
                   'r-', linewidth=2, label=f'Tendencia\n(r={r_value:.3f})')

            ax.set_xlabel('Muestras', fontsize=7)
            ax.set_ylabel('Valor', fontsize=7)
            ax.set_title('Análisis de\nTendencias', fontsize=9, fontweight='bold')
            ax.legend(fontsize=6)
            ax.grid(True, alpha=0.3)
            ax.tick_params(labelsize=6)

    def _plot_stability_analysis(self, ax, var_name):
        """Panel 6: Análisis de estabilidad (rolling statistics)"""
        if not var_name or len(self.csv_data) < 50:
            ax.text(0.5, 0.5, 'Datos insuficientes\n(mín 50 pts)', ha='center', va='center', transform=ax.transAxes)
            ax.set_title('Estabilidad')
            ax.axis('off')
            return

        data = self.csv_data[var_name].dropna()
        if len(data) >= 50:
            window = min(20, len(data)//5)
            rolling_mean = data.rolling(window=window, center=True).mean()
            rolling_std = data.rolling(window=window, center=True).std()

            ax.plot(data.index, rolling_mean, 'b-', linewidth=2, label=f'Media móvil\n(ventana={window})')
            ax.fill_between(data.index,
                          rolling_mean - rolling_std,
                          rolling_mean + rolling_std,
                          alpha=0.3, color='blue', label='±1σ')

            ax.set_xlabel('Índice', fontsize=7)
            ax.set_ylabel('Valor', fontsize=7)
            ax.set_title('Estabilidad\n(Rolling Stats)', fontsize=9, fontweight='bold')
            ax.legend(fontsize=6)
            ax.grid(True, alpha=0.3)
            ax.tick_params(labelsize=6)

    def _plot_normality_tests(self, ax, available_vars):
        """Panel 7: Tests de normalidad"""
        if not available_vars:
            ax.text(0.5, 0.5, 'Sin datos', ha='center', va='center', transform=ax.transAxes)
            ax.set_title('Normalidad')
            ax.axis('off')
            return

        normality_results = []
        for var in available_vars[:3]:  # Limitar a 3 variables
            data = self.csv_data[var].dropna()
            if len(data) >= 8:  # Mínimo para test Shapiro-Wilk
                try:
                    from scipy import stats
                    stat, p_value = stats.shapiro(data)
                    is_normal = p_value > 0.05
                    normality_results.append({
                        'Var': var.split('(')[0][:8],
                        'Normal': 'Sí' if is_normal else 'No',
                        'p-valor': f'{p_value:.3f}'
                    })
                except:
                    normality_results.append({
                        'Var': var.split('(')[0][:8],
                        'Normal': 'N/A',
                        'p-valor': 'Error'
                    })

        if normality_results:
            df_norm = pd.DataFrame(normality_results)
            ax.axis('tight')
            ax.axis('off')

            colors = [['lightgreen' if row['Normal'] == 'Sí' else 'lightcoral' for row in normality_results]]
            table = ax.table(cellText=df_norm.values,
                           colLabels=df_norm.columns,
                           cellLoc='center',
                           loc='center')

            table.auto_set_font_size(False)
            table.set_fontsize(7)
            table.scale(1, 1.2)

        ax.set_title('Tests de\nNormalidad', fontsize=9, fontweight='bold')

    def _plot_outlier_analysis(self, ax, var_name):
        """Panel 8: Análisis de outliers"""
        if not var_name:
            ax.text(0.5, 0.5, 'Sin datos', ha='center', va='center', transform=ax.transAxes)
            ax.set_title('Outliers')
            ax.axis('off')
            return

        data = self.csv_data[var_name].dropna()
        if len(data) > 0:
            # Método IQR para detectar outliers
            Q1 = np.percentile(data, 25)
            Q3 = np.percentile(data, 75)
            IQR = Q3 - Q1

            lower_bound = Q1 - 1.5 * IQR
            upper_bound = Q3 + 1.5 * IQR

            outliers = data[(data < lower_bound) | (data > upper_bound)]
            inliers = data[(data >= lower_bound) & (data <= upper_bound)]

            # Plot
            ax.scatter(inliers.index, inliers, alpha=0.6, s=15, color='blue', label='Datos normales')
            if len(outliers) > 0:
                ax.scatter(outliers.index, outliers, color='red', s=25, marker='x',
                          linewidth=2, label=f'Outliers ({len(outliers)})')

            # Líneas de límites
            ax.axhline(y=lower_bound, color='orange', linestyle='--', alpha=0.7, linewidth=1)
            ax.axhline(y=upper_bound, color='orange', linestyle='--', alpha=0.7, linewidth=1)
            ax.axhline(y=Q1, color='green', linestyle=':', alpha=0.7, linewidth=1)
            ax.axhline(y=Q3, color='green', linestyle=':', alpha=0.7, linewidth=1)

            ax.set_xlabel('Índice', fontsize=7)
            ax.set_ylabel('Valor', fontsize=7)
            ax.set_title('Análisis de\nOutliers (IQR)', fontsize=9, fontweight='bold')
            ax.legend(fontsize=6)
            ax.grid(True, alpha=0.3)
            ax.tick_params(labelsize=6)

    def _plot_time_correlation(self, ax, available_vars):
        """Panel 9: Correlación con tiempo"""
        if not available_vars or 'Sample' not in self.csv_data.columns:
            ax.text(0.5, 0.5, 'Sin datos\ntemporales', ha='center', va='center', transform=ax.transAxes)
            ax.set_title('Correlación\nTemporal')
            ax.axis('off')
            return

        time_data = self.csv_data['Sample'].values
        corr_results = []

        for var in available_vars[:4]:  # Máximo 4 variables
            data = self.csv_data[var].dropna()
            if len(data) > 5:
                # Correlación con tiempo
                corr = np.corrcoef(time_data[:len(data)], data)[0, 1]
                corr_results.append({
                    'Variable': var.split('(')[0][:10],
                    'Corr_Tiempo': corr
                })

        if corr_results:
            df_corr = pd.DataFrame(corr_results)
            ax.axis('tight')
            ax.axis('off')

            table = ax.table(cellText=df_corr.round(3).values,
                           colLabels=['Variable', 'Corr\nTiempo'],
                           cellLoc='center',
                           loc='center',
                           colColours=['lightyellow', 'lightyellow'])

            table.auto_set_font_size(False)
            table.set_fontsize(7)
            table.scale(1, 1.2)

        ax.set_title('Correlación\ncon Tiempo', fontsize=9, fontweight='bold')

    def _plot_autocorrelation(self, ax, var_name):
        """Panel 10: Análisis de autocorrelación"""
        if not var_name or len(self.csv_data) < 30:
            ax.text(0.5, 0.5, 'Datos insuficientes\n(mín 30 pts)', ha='center', va='center', transform=ax.transAxes)
            ax.set_title('Autocorrelación')
            ax.axis('off')
            return

        data = self.csv_data[var_name].dropna()
        if len(data) >= 30:
            try:
                from scipy import signal
                # Calcular autocorrelación
                autocorr = signal.correlate(data - np.mean(data), data - np.mean(data), mode='full')
                autocorr = autocorr[autocorr.size // 2:]  # Solo lags positivos
                autocorr = autocorr / autocorr[0]  # Normalizar

                lags = np.arange(len(autocorr))
                max_lag = min(50, len(autocorr))  # Mostrar máximo 50 lags

                ax.plot(lags[:max_lag], autocorr[:max_lag], 'b-', linewidth=1.5)
                ax.axhline(y=0.1, color='red', linestyle='--', alpha=0.7, linewidth=1, label='Umbral 0.1')
                ax.axhline(y=-0.1, color='red', linestyle='--', alpha=0.7, linewidth=1)

                ax.set_xlabel('Lag', fontsize=7)
                ax.set_ylabel('Autocorr', fontsize=7)
                ax.set_title('Autocorrelación', fontsize=9, fontweight='bold')
                ax.legend(fontsize=6)
                ax.grid(True, alpha=0.3)
                ax.tick_params(labelsize=6)

            except ImportError:
                ax.text(0.5, 0.5, 'scipy no disponible\npara autocorrelación', ha='center', va='center', transform=ax.transAxes)
                ax.set_title('Autocorrelación')
                ax.axis('off')

    def _plot_variance_analysis(self, ax, available_vars):
        """Panel 11: Análisis de varianza"""
        if not available_vars:
            ax.text(0.5, 0.5, 'Sin datos', ha='center', va='center', transform=ax.transAxes)
            ax.set_title('Análisis de\nVarianza')
            ax.axis('off')
            return

        variance_data = []
        for var in available_vars[:4]:  # Máximo 4 variables
            data = self.csv_data[var].dropna()
            if len(data) > 0:
                variance_data.append({
                    'Var': var.split('(')[0][:8],
                    'Varianza': np.var(data),
                    'Coef_Var': np.std(data) / abs(np.mean(data)) if np.mean(data) != 0 else 0
                })

        if variance_data:
            df_var = pd.DataFrame(variance_data)

            # Crear gráfico de barras para varianza
            bars = ax.bar(range(len(df_var)), df_var['Varianza'],
                         color=['skyblue', 'lightgreen', 'lightcoral', 'gold'][:len(df_var)],
                         alpha=0.7, edgecolor='black', linewidth=0.5)

            ax.set_xticks(range(len(df_var)))
            ax.set_xticklabels(df_var['Var'], rotation=45, ha='right', fontsize=7)
            ax.set_ylabel('Varianza', fontsize=7)
            ax.set_title('Análisis de\nVarianza', fontsize=9, fontweight='bold')
            ax.grid(True, axis='y', alpha=0.3)
            ax.tick_params(labelsize=6)

            # Añadir valores en las barras
            for i, bar in enumerate(bars):
                height = bar.get_height()
                ax.text(bar.get_x() + bar.get_width()/2., height + height*0.01,
                       '.2e', ha='center', va='bottom', fontsize=6, rotation=90)

    def _plot_percentile_comparison(self, ax, available_vars, var_labels):
        """Panel 12: Comparación de percentiles"""
        if not available_vars:
            ax.text(0.5, 0.5, 'Sin datos', ha='center', va='center', transform=ax.transAxes)
            ax.set_title('Percentiles')
            ax.axis('off')
            return

        percentiles = [10, 25, 50, 75, 90]
        perc_data = []

        for var in available_vars[:3]:  # Máximo 3 variables
            data = self.csv_data[var].dropna()
            if len(data) > 0:
                perc_values = np.percentile(data, percentiles)
                perc_data.append(perc_values)

        if perc_data:
            perc_array = np.array(perc_data)

            for i, (var, values) in enumerate(zip(available_vars[:3], perc_data)):
                label = var_labels[available_vars.index(var)][:12]
                ax.plot(percentiles, values, 'o-', linewidth=2, markersize=4,
                       label=label, alpha=0.8)

            ax.set_xlabel('Percentil', fontsize=7)
            ax.set_ylabel('Valor', fontsize=7)
            ax.set_title('Comparación\nde Percentiles', fontsize=9, fontweight='bold')
            ax.legend(fontsize=6)
            ax.grid(True, alpha=0.3)
            ax.tick_params(labelsize=6)

    def _plot_skewness_kurtosis(self, ax, available_vars, var_labels):
        """Panel 13: Análisis de skewness y kurtosis"""
        if not available_vars:
            ax.text(0.5, 0.5, 'Sin datos', ha='center', va='center', transform=ax.transAxes)
            ax.set_title('Asimetría y\nCurtosis')
            ax.axis('off')
            return

        try:
            from scipy import stats

            skew_data = []
            kurt_data = []

            for var in available_vars[:4]:  # Máximo 4 variables
                data = self.csv_data[var].dropna()
                if len(data) > 3:
                    skew_val = stats.skew(data)
                    kurt_val = stats.kurtosis(data)
                    skew_data.append(skew_val)
                    kurt_data.append(kurt_val)

            if skew_data:
                x = np.arange(len(skew_data))
                width = 0.35

                ax.bar(x - width/2, skew_data, width, label='Asimetría',
                      color='lightblue', alpha=0.7, edgecolor='black', linewidth=0.5)
                ax.bar(x + width/2, kurt_data, width, label='Curtosis',
                      color='lightgreen', alpha=0.7, edgecolor='black', linewidth=0.5)

                ax.set_xticks(x)
                ax.set_xticklabels([var_labels[available_vars.index(v)][:8] for v in available_vars[:4]],
                                 rotation=45, ha='right', fontsize=6)
                ax.set_ylabel('Valor', fontsize=7)
                ax.set_title('Asimetría y\nCurtosis', fontsize=9, fontweight='bold')
                ax.legend(fontsize=6)
                ax.grid(True, axis='y', alpha=0.3)
                ax.axhline(y=0, color='red', linestyle='--', alpha=0.5, linewidth=1)
                ax.tick_params(labelsize=6)

        except ImportError:
            ax.text(0.5, 0.5, 'scipy no disponible\npara estadísticas', ha='center', va='center', transform=ax.transAxes)
            ax.set_title('Asimetría y\nCurtosis')
            ax.axis('off')

    def _plot_key_statistics(self, ax, available_vars, var_labels):
        """Panel 14: Resumen de estadísticas clave"""
        if not available_vars:
            ax.text(0.5, 0.5, 'Sin datos', ha='center', va='center', transform=ax.transAxes)
            ax.set_title('Estadísticas\nClave')
            ax.axis('off')
            return

        key_stats = []
        for var in available_vars[:2]:  # Solo 2 variables principales
            data = self.csv_data[var].dropna()
            if len(data) > 0:
                key_stats.append({
                    'Métrica': ['Media', 'Std', 'CV%', 'Rango'],
                    'Valor': [np.mean(data),
                             np.std(data),
                             np.std(data)/abs(np.mean(data))*100 if np.mean(data) != 0 else 0,
                             np.max(data) - np.min(data)]
                })

        if key_stats:
            # Crear tabla con métricas clave
            metrics = key_stats[0]['Métrica']
            values = key_stats[0]['Valor']

            ax.axis('tight')
            ax.axis('off')

            table_data = [[f'{val:.3f}' for val in values]]
            table = ax.table(cellText=table_data,
                           colLabels=metrics,
                           cellLoc='center',
                           loc='center',
                           colColours=['lightcyan'] * len(metrics))

            table.auto_set_font_size(False)
            table.set_fontsize(8)
            table.scale(1, 1.5)

        ax.set_title('Estadísticas\nClave', fontsize=9, fontweight='bold')

    def _plot_dynamic_range(self, ax, available_vars, var_labels):
        """Panel 15: Análisis de rangos dinámicos"""
        if not available_vars:
            ax.text(0.5, 0.5, 'Sin datos', ha='center', va='center', transform=ax.transAxes)
            ax.set_title('Rango\nDinámico')
            ax.axis('off')
            return

        range_data = []
        for var in available_vars[:4]:  # Máximo 4 variables
            data = self.csv_data[var].dropna()
            if len(data) > 0:
                v_min, v_max = np.min(data), np.max(data)
                v_range = v_max - v_min
                v_mean = np.mean(data)
                dynamic_range = v_range / abs(v_mean) if v_mean != 0 else 0

                range_data.append({
                    'Var': var_labels[available_vars.index(var)][:10],
                    'Rango': v_range,
                    'Dinámico': dynamic_range
                })

        if range_data:
            df_range = pd.DataFrame(range_data)

            # Gráfico de barras para rangos
            bars = ax.bar(range(len(df_range)), df_range['Rango'],
                         color=['skyblue', 'lightgreen', 'lightcoral', 'gold'][:len(df_range)],
                         alpha=0.7, edgecolor='black', linewidth=0.5)

            ax.set_xticks(range(len(df_range)))
            ax.set_xticklabels(df_range['Var'], rotation=45, ha='right', fontsize=7)
            ax.set_ylabel('Rango', fontsize=7)
            ax.set_title('Rango\nDinámico', fontsize=9, fontweight='bold')
            ax.grid(True, axis='y', alpha=0.3)
            ax.tick_params(labelsize=6)

            # Añadir valores
            for i, bar in enumerate(bars):
                height = bar.get_height()
                ax.text(bar.get_x() + bar.get_width()/2., height + height*0.01,
                       '.2e', ha='center', va='bottom', fontsize=6, rotation=90)

    def _plot_statistical_summary(self, ax, available_vars, var_labels):
        """Panel 16: Matriz de resumen estadístico"""
        if not available_vars:
            ax.text(0.5, 0.5, 'Sin datos', ha='center', va='center', transform=ax.transAxes)
            ax.set_title('Resumen\nEstadístico')
            ax.axis('off')
            return

        # Crear resumen compacto
        summary_data = []
        for var in available_vars[:2]:  # Solo 2 variables principales
            data = self.csv_data[var].dropna()
            if len(data) > 0:
                summary_data.append([
                    var_labels[available_vars.index(var)][:12],
                    '.3f',
                    '.3f',
                    '.3f',
                    '.3f'
                ])

        if summary_data:
            ax.axis('tight')
            ax.axis('off')

            table = ax.table(cellText=summary_data,
                           colLabels=['Variable', 'Media', 'Std', 'Min', 'Max'],
                           cellLoc='center',
                           loc='center',
                           colColours=['lightgray', 'lightblue', 'lightblue', 'lightblue', 'lightblue'])

            table.auto_set_font_size(False)
            table.set_fontsize(6)
            table.scale(1, 1.0)

        ax.set_title('Resumen\nEstadístico', fontsize=9, fontweight='bold')

    def _plot_individual_histograms(self, ax, available_vars, var_labels):
        """Panel: Histogramas individuales con ajuste de distribución normal"""
        if not available_vars:
            ax.text(0.5, 0.5, 'No hay datos disponibles', ha='center', va='center', fontsize=10)
            ax.set_title('Histogramas\nIndividuales', fontsize=9, fontweight='bold')
            return

        # Tomar las primeras 3 variables para mostrar en un solo panel
        vars_to_plot = available_vars[:3]

        colors = ['skyblue', 'lightcoral', 'lightgreen']
        alpha = 0.7

        for i, var in enumerate(vars_to_plot):
            data = self.csv_data[var].dropna()
            if len(data) > 10:
                # Histograma
                n, bins, patches = ax.hist(data, bins=30, alpha=alpha, color=colors[i % len(colors)],
                                         label=var_labels.get(var, var), density=True)

                # Ajuste de distribución normal (opcional, requiere scipy)
                try:
                    mu, std = stats.norm.fit(data)
                    xmin, xmax = ax.get_xlim()
                    x = np.linspace(xmin, xmax, 100)
                    p = stats.norm.pdf(x, mu, std)
                    ax.plot(x, p, color=colors[i % len(colors)], linewidth=2, linestyle='--',
                           label=f'{var_labels.get(var, var)} Normal')
                except (ImportError, AttributeError):
                    pass  # Si scipy no está disponible, solo mostrar histograma

        ax.set_xlabel('Valor', fontsize=8)
        ax.set_ylabel('Densidad', fontsize=8)
        ax.set_title('Histogramas con\nAjuste Normal', fontsize=9, fontweight='bold')
        ax.legend(fontsize=6)
        ax.grid(True, alpha=0.3)
        ax.tick_params(labelsize=7)

    def plot_snr_raw(self):
        """Análisis comprehensivo de SNR para señal TIVA Raw vs Keithley"""
        required_cols = ['Sample', 'KEITHLEY Voltage (V)', 'TIVA Voltage (V)']
        missing_cols = [col for col in required_cols if col not in self.csv_data.columns]

        if missing_cols or len(self.csv_data) < 50:
            fig, ax = plt.subplots(figsize=(8, 6))
            if missing_cols:
                ax.text(0.5, 0.5, f'Columnas faltantes: {", ".join(missing_cols)}',
                       transform=ax.transAxes, ha='center', va='center', fontsize=12,
                       bbox=dict(boxstyle="round,pad=0.3", facecolor="lightcoral", alpha=0.5))
            else:
                ax.text(0.5, 0.5, f'Datos insuficientes (mínimo 50 puntos)\nPuntos disponibles: {len(self.csv_data)}',
                       transform=ax.transAxes, ha='center', va='center', fontsize=12,
                       bbox=dict(boxstyle="round,pad=0.3", facecolor="lightcoral", alpha=0.5))
            ax.set_title('SNR TIVA Raw - Datos Insuficientes')
            ax.set_xlim(0, 1)
            ax.set_ylim(0, 1)
            ax.axis('off')
        else:
            # Crear figura con layout 4x4 para análisis comprehensivo
            fig = plt.figure(figsize=(14, 10), dpi=100)  # Tamaño más razonable
            fig.suptitle('Análisis Comprehensivo SNR - TIVA Raw vs Keithley', fontsize=14, fontweight='bold')

            # Preparar datos
            samples = self.csv_data['Sample'].values
            keithley_voltage = self.csv_data['KEITHLEY Voltage (V)'].values
            tiva_raw = self.csv_data['TIVA Voltage (V)'].values

            # Panel 1: Evolución temporal del SNR
            ax1 = plt.subplot(4, 4, 1)
            self._plot_snr_temporal(ax1, keithley_voltage, tiva_raw, samples, 'Raw')

            # Panel 2: Componentes de señal (señal vs ruido)
            ax2 = plt.subplot(4, 4, 2)
            self._plot_signal_components(ax2, keithley_voltage, tiva_raw, samples)

            # Panel 3: Histogramas de SNR
            ax3 = plt.subplot(4, 4, 3)
            self._plot_snr_histogram(ax3, keithley_voltage, tiva_raw, samples)

            # Panel 4: Análisis de estabilidad SNR
            ax4 = plt.subplot(4, 4, 4)
            self._plot_snr_stability(ax4, keithley_voltage, tiva_raw, samples)

            # Panel 5: Comparación de métodos SNR
            ax5 = plt.subplot(4, 4, 5)
            self._plot_snr_methods_comparison(ax5, keithley_voltage, tiva_raw, samples)

            # Panel 6: Análisis de ruido
            ax6 = plt.subplot(4, 4, 6)
            self._plot_noise_analysis(ax6, keithley_voltage, tiva_raw, samples)

            # Panel 7: SNR vs amplitud de señal
            ax7 = plt.subplot(4, 4, 7)
            self._plot_snr_vs_amplitude(ax7, keithley_voltage, tiva_raw, samples)

            # Panel 8: Detección de outliers en SNR
            ax8 = plt.subplot(4, 4, 8)
            self._plot_snr_outliers(ax8, keithley_voltage, tiva_raw, samples)

            # Panel 9: Autocorrelación del ruido
            ax9 = plt.subplot(4, 4, 9)
            self._plot_noise_autocorr(ax9, keithley_voltage, tiva_raw)

            # Panel 10: Espectro del ruido
            ax10 = plt.subplot(4, 4, 10)
            self._plot_noise_spectrum(ax10, keithley_voltage, tiva_raw, samples)

            # Panel 11: Métricas de calidad de señal
            ax11 = plt.subplot(4, 4, 11)
            self._plot_signal_quality_metrics(ax11, keithley_voltage, tiva_raw, samples)

            # Panel 12: Análisis de tendencias SNR
            ax12 = plt.subplot(4, 4, 12)
            self._plot_snr_trends(ax12, keithley_voltage, tiva_raw, samples)

            # Panel 14: Resumen estadístico SNR
            ax14 = plt.subplot(4, 4, 14)
            self._plot_snr_summary_stats(ax14, keithley_voltage, tiva_raw, samples)

            # Panel 15: Análisis de variabilidad
            ax15 = plt.subplot(4, 4, 15)
            self._plot_snr_variability(ax15, keithley_voltage, tiva_raw, samples)

            # Panel 16: Matriz de correlación de métricas
            ax16 = plt.subplot(4, 4, 16)
            self._plot_snr_correlation_matrix(ax16, keithley_voltage, tiva_raw, samples)

            plt.tight_layout(h_pad=0.3)

        # Crear canvas y añadir a la interfaz        # Crear canvas usando el nuevo sistema de pestañas
        self.create_analysis_canvas(fig, 'correlation')

    def _plot_snr_temporal(self, ax, ref_signal, meas_signal, samples, signal_type):
        """Panel: Evolución temporal del SNR"""
        times, snr = self.calculate_snr_sliding(ref_signal, meas_signal, samples, window_size=30, step=5)

        if snr:
            ax.plot(times, snr, 'b-', linewidth=2, alpha=0.8)
            ax.fill_between(times, snr, alpha=0.3, color='blue')

            # Líneas de referencia
            ax.axhline(y=np.mean(snr), color='red', linestyle='--', alpha=0.7,
                      label=f'Promedio: {np.mean(snr):.1f} dB')
            ax.axhline(y=np.median(snr), color='orange', linestyle=':', alpha=0.7,
                      label=f'Mediana: {np.median(snr):.1f} dB')

            ax.set_xlabel('Muestras', fontsize=8)
            ax.set_ylabel('SNR (dB)', fontsize=8)
            ax.set_title(f'SNR Temporal\n{signal_type}', fontsize=9, fontweight='bold')
            ax.legend(fontsize=6)
            ax.grid(True, alpha=0.3)
            ax.tick_params(labelsize=7)

    def _plot_signal_components(self, ax, ref_signal, meas_signal, samples):
        """Panel: Componentes de señal (señal vs ruido)"""
        # Calcular ruido como diferencia
        noise = meas_signal - ref_signal

        # Plot de las tres componentes
        ax.plot(samples, ref_signal, 'g-', linewidth=1.5, label='Señal Ref (Keithley)', alpha=0.8)
        ax.plot(samples, meas_signal, 'b-', linewidth=1.5, label='Señal TIVA Raw', alpha=0.8)
        ax.plot(samples, noise, 'r-', linewidth=1, label='Ruido', alpha=0.7)

        ax.set_xlabel('Muestras', fontsize=8)
        ax.set_ylabel('Amplitud (V)', fontsize=8)
        ax.set_title('Componentes\nde Señal', fontsize=9, fontweight='bold')
        ax.legend(fontsize=6)
        ax.grid(True, alpha=0.3)
        ax.tick_params(labelsize=7)

    def _plot_signal_components_filtered(self, ax, ref_signal, meas_signal, samples):
        """Panel: Componentes de señal mejoradas por filtro"""
        # Calcular ruido residual
        noise = meas_signal - ref_signal

        # Comparar con señal raw si está disponible
        if 'TIVA Voltage (V)' in self.csv_data.columns:
            raw_signal = self.csv_data['TIVA Voltage (V)'].values
            raw_noise = raw_signal - ref_signal

            ax.plot(samples, raw_noise, 'r-', linewidth=1, label='Ruido Raw', alpha=0.5)
            ax.plot(samples, noise, 'orange', linewidth=1.5, label='Ruido Filtrado', alpha=0.8)
        else:
            ax.plot(samples, noise, 'orange', linewidth=1.5, label='Ruido Residual', alpha=0.8)

        ax.set_xlabel('Muestras', fontsize=8)
        ax.set_ylabel('Ruido (V)', fontsize=8)
        ax.set_title('Ruido Residual\nFiltrado', fontsize=9, fontweight='bold')
        ax.legend(fontsize=6)
        ax.grid(True, alpha=0.3)
        ax.tick_params(labelsize=7)

    def _plot_snr_histogram(self, ax, ref_signal, meas_signal, samples):
        """Panel: Histograma de valores SNR"""
        times, snr = self.calculate_snr_sliding(ref_signal, meas_signal, samples, window_size=25, step=5)

        if snr:
            n, bins, patches = ax.hist(snr, bins=15, alpha=0.7, color='skyblue', edgecolor='black', density=True)

            # Añadir línea de densidad si scipy está disponible
            try:
                from scipy import stats
                kde_x = np.linspace(min(snr), max(snr), 100)
                kde = stats.gaussian_kde(snr)
                ax.plot(kde_x, kde(kde_x), 'r-', linewidth=2, label='KDE')
            except:
                pass

            ax.axvline(np.mean(snr), color='red', linestyle='--', linewidth=2,
                      label=f'μ: {np.mean(snr):.1f}')
            ax.axvline(np.median(snr), color='orange', linestyle=':', linewidth=2,
                      label=f'Mediana: {np.median(snr):.1f}')

            ax.set_xlabel('SNR (dB)', fontsize=8)
            ax.set_ylabel('Densidad', fontsize=8)
            ax.set_title('Distribución\nSNR', fontsize=9, fontweight='bold')
            ax.legend(fontsize=6)
            ax.grid(True, alpha=0.3)
            ax.tick_params(labelsize=7)

    def _plot_snr_stability(self, ax, ref_signal, meas_signal, samples):
        """Panel: Análisis de estabilidad del SNR"""
        times, snr = self.calculate_snr_sliding(ref_signal, meas_signal, samples, window_size=20, step=2)

        if snr and len(snr) > 10:
            # Calcular estadísticas móviles
            window_stats = 5
            rolling_mean = pd.Series(snr).rolling(window=window_stats, center=True).mean()
            rolling_std = pd.Series(snr).rolling(window=window_stats, center=True).std()

            ax.plot(times, snr, 'b-', alpha=0.5, linewidth=1, label='SNR')
            ax.plot(times, rolling_mean, 'r-', linewidth=2, label=f'Media móvil\n({window_stats} pts)')
            ax.fill_between(times,
                          rolling_mean - rolling_std,
                          rolling_mean + rolling_std,
                          alpha=0.3, color='red', label='±1σ')

            ax.set_xlabel('Muestras', fontsize=8)
            ax.set_ylabel('SNR (dB)', fontsize=8)
            ax.set_title('Estabilidad\nSNR', fontsize=9, fontweight='bold')
            ax.legend(fontsize=6)
            ax.grid(True, alpha=0.3)
            ax.tick_params(labelsize=7)

    def _plot_snr_methods_comparison(self, ax, ref_signal, meas_signal, samples):
        """Panel: Comparación de diferentes métodos de cálculo SNR"""
        if len(ref_signal) < 30:
            ax.text(0.5, 0.5, 'Datos insuficientes\npara comparación', ha='center', va='center', transform=ax.transAxes)
            ax.set_title('Comparación\nMétodos SNR')
            ax.axis('off')
            return

        # Método 1: Ventana deslizante (actual)
        times1, snr1 = self.calculate_snr_sliding(ref_signal, meas_signal, samples, window_size=25, step=5)

        # Método 2: SNR global
        noise_global = meas_signal - ref_signal
        var_signal_global = np.var(ref_signal)
        var_noise_global = np.var(noise_global)
        snr_global = 10 * np.log10(var_signal_global / var_noise_global) if var_noise_global > 0 else 50
        snr2 = [snr_global] * len(times1)

        # Método 3: SNR por segmentos
        segment_size = len(ref_signal) // 4
        snr3 = []
        times3 = []
        for i in range(0, len(ref_signal) - segment_size + 1, segment_size // 2):
            end_idx = min(i + segment_size, len(ref_signal))
            seg_ref = ref_signal[i:end_idx]
            seg_meas = meas_signal[i:end_idx]

            noise_seg = seg_meas - seg_ref
            var_sig = np.var(seg_ref)
            var_noise = np.var(noise_seg)

            if var_noise > 0:
                snr_val = 10 * np.log10(var_sig / var_noise)
            else:
                snr_val = 50

            snr3.append(snr_val)
            times3.append(np.mean(samples[i:end_idx]))

        # Plot comparación
        if snr1:
            ax.plot(times1, snr1, 'b-', linewidth=2, label='Ventana deslizante')
        if snr2:
            ax.plot(times1, snr2, 'r--', linewidth=2, label='Global')
        if snr3:
            ax.plot(times3, snr3, 'g:', linewidth=2, label='Por segmentos')

        ax.set_xlabel('Muestras', fontsize=8)
        ax.set_ylabel('SNR (dB)', fontsize=8)
        ax.set_title('Comparación\nMétodos SNR', fontsize=9, fontweight='bold')
        ax.legend(fontsize=6)
        ax.grid(True, alpha=0.3)
        ax.tick_params(labelsize=7)

    def _plot_noise_analysis(self, ax, ref_signal, meas_signal, samples):
        """Panel: Análisis detallado del ruido"""
        noise = meas_signal - ref_signal

        # Estadísticas del ruido
        noise_stats = {
            'Media': np.mean(noise),
            'Std': np.std(noise),
            'RMS': np.sqrt(np.mean(noise**2)),
            'Max': np.max(np.abs(noise))
        }

        # Crear tabla de estadísticas
        ax.axis('tight')
        ax.axis('off')

        table_data = [[f'{val:.2e}' for val in noise_stats.values()]]
        table = ax.table(cellText=table_data,
                        colLabels=list(noise_stats.keys()),
                        cellLoc='center',
                        loc='center',
                        colColours=['lightcoral'] * len(noise_stats))

        table.auto_set_font_size(False)
        table.set_fontsize(8)
        table.scale(1, 1.5)

        ax.set_title('Estadísticas\ndel Ruido', fontsize=9, fontweight='bold')

    def _plot_noise_analysis_filtered(self, ax, ref_signal, meas_signal, samples):
        """Panel: Análisis del ruido residual después del filtrado"""
        noise = meas_signal - ref_signal

        # Comparar con ruido de señal raw si está disponible
        comparison_data = {}
        if 'TIVA Voltage (V)' in self.csv_data.columns:
            raw_signal = self.csv_data['TIVA Voltage (V)'].values
            raw_noise = raw_signal - ref_signal

            comparison_data = {
                'Raw': {
                    'RMS': np.sqrt(np.mean(raw_noise**2)),
                    'Std': np.std(raw_noise),
                    'Max': np.max(np.abs(raw_noise))
                },
                'Filtrado': {
                    'RMS': np.sqrt(np.mean(noise**2)),
                    'Std': np.std(noise),
                    'Max': np.max(np.abs(noise))
                }
            }

            # Calcular mejora
            improvement = {}
            for metric in ['RMS', 'Std', 'Max']:
                raw_val = comparison_data['Raw'][metric]
                filt_val = comparison_data['Filtrado'][metric]
                improvement[metric] = (raw_val - filt_val) / raw_val * 100 if raw_val != 0 else 0

            comparison_data['Mejora %'] = improvement

        # Mostrar tabla de comparación
        if comparison_data:
            df_comp = pd.DataFrame(comparison_data).round(2)
            ax.axis('tight')
            ax.axis('off')

            table = ax.table(cellText=df_comp.values,
                           colLabels=df_comp.columns,
                           cellLoc='center',
                           loc='center')

            table.auto_set_font_size(False)
            table.set_fontsize(7)
            table.scale(1, 1.2)

        ax.set_title('Ruido: Raw vs\nFiltrado', fontsize=9, fontweight='bold')

    def _plot_snr_vs_amplitude(self, ax, ref_signal, meas_signal, samples):
        """Panel: Relación entre SNR y amplitud de señal"""
        times, snr = self.calculate_snr_sliding(ref_signal, meas_signal, samples, window_size=20, step=5)

        if snr and len(snr) > 5:
            # Calcular amplitud de señal en cada ventana
            amplitudes = []
            for i in range(0, len(ref_signal) - 20 + 1, 5):
                window_signal = ref_signal[i:i+20]
                amplitudes.append(np.max(window_signal) - np.min(window_signal))

            # Ajustar longitudes
            min_len = min(len(snr), len(amplitudes))
            snr_trimmed = snr[:min_len]
            amp_trimmed = amplitudes[:min_len]

            # Scatter plot con línea de tendencia
            ax.scatter(amp_trimmed, snr_trimmed, alpha=0.6, s=20, color='blue')

            # Tendencia lineal
            try:
                from scipy import stats
                slope, intercept, r_value, p_value, std_err = stats.linregress(amp_trimmed, snr_trimmed)
                x_trend = np.linspace(min(amp_trimmed), max(amp_trimmed), 100)
                y_trend = intercept + slope * x_trend
                ax.plot(x_trend, y_trend, 'r-', linewidth=2,
                       label=f'r = {r_value:.2f}')
            except:
                pass

            ax.set_xlabel('Amplitud Señal (V)', fontsize=8)
            ax.set_ylabel('SNR (dB)', fontsize=8)
            ax.set_title('SNR vs\nAmplitud', fontsize=9, fontweight='bold')
            ax.legend(fontsize=6)
            ax.grid(True, alpha=0.3)
            ax.tick_params(labelsize=7)

    def _plot_snr_outliers(self, ax, ref_signal, meas_signal, samples):
        """Panel: Detección de outliers en SNR"""
        times, snr = self.calculate_snr_sliding(ref_signal, meas_signal, samples, window_size=20, step=5)

        if snr and len(snr) > 10:
            # Detectar outliers usando IQR
            Q1 = np.percentile(snr, 25)
            Q3 = np.percentile(snr, 75)
            IQR = Q3 - Q1

            lower_bound = Q1 - 1.5 * IQR
            upper_bound = Q3 + 1.5 * IQR

            outliers = [(t, s) for t, s in zip(times, snr) if s < lower_bound or s > upper_bound]
            inliers = [(t, s) for t, s in zip(times, snr) if lower_bound <= s <= upper_bound]

            # Plot
            if inliers:
                t_in, s_in = zip(*inliers)
                ax.scatter(t_in, s_in, alpha=0.6, s=15, color='blue', label='SNR normal')
            if outliers:
                t_out, s_out = zip(*outliers)
                ax.scatter(t_out, s_out, color='red', s=25, marker='x',
                          linewidth=2, label=f'Outliers ({len(outliers)})')

            # Líneas de límites
            ax.axhline(y=lower_bound, color='orange', linestyle='--', alpha=0.7, linewidth=1)
            ax.axhline(y=upper_bound, color='orange', linestyle='--', alpha=0.7, linewidth=1)
            ax.axhline(y=Q1, color='green', linestyle=':', alpha=0.7, linewidth=1)
            ax.axhline(y=Q3, color='green', linestyle=':', alpha=0.7, linewidth=1)

            ax.set_xlabel('Muestras', fontsize=8)
            ax.set_ylabel('SNR (dB)', fontsize=8)
            ax.set_title('Outliers\nen SNR', fontsize=9, fontweight='bold')
            ax.legend(fontsize=6)
            ax.grid(True, alpha=0.3)
            ax.tick_params(labelsize=7)

    def _plot_noise_autocorr(self, ax, ref_signal, meas_signal):
        """Panel: Autocorrelación del ruido"""
        # Asegurar que sean arrays de numpy
        ref_signal = np.asarray(ref_signal)
        meas_signal = np.asarray(meas_signal)
        
        noise = meas_signal - ref_signal

        if len(noise) >= 30:
            try:
                from scipy import signal
                # Calcular autocorrelación
                noise_centered = noise - np.mean(noise)
                autocorr = signal.correlate(noise_centered, noise_centered, mode='full')
                autocorr = autocorr[autocorr.size // 2:]  # Solo lags positivos
                autocorr = autocorr / autocorr[0]  # Normalizar

                lags = np.arange(len(autocorr))
                max_lag = min(50, len(autocorr))  # Mostrar máximo 50 lags

                ax.plot(lags[:max_lag], autocorr[:max_lag], 'b-', linewidth=1.5)
                ax.axhline(y=0.1, color='red', linestyle='--', alpha=0.7, linewidth=1, label='Umbral 0.1')
                ax.axhline(y=-0.1, color='red', linestyle='--', alpha=0.7, linewidth=1)

                ax.set_xlabel('Lag', fontsize=8)
                ax.set_ylabel('Autocorr', fontsize=8)
                ax.set_title('Autocorrelación\ndel Ruido', fontsize=9, fontweight='bold')
                ax.legend(fontsize=6)
                ax.grid(True, alpha=0.3)
                ax.tick_params(labelsize=7)

            except ImportError:
                ax.text(0.5, 0.5, 'scipy no disponible\npara autocorrelación', ha='center', va='center', transform=ax.transAxes)
                ax.set_title('Autocorrelación\ndel Ruido')
                ax.axis('off')

    def _plot_noise_spectrum(self, ax, ref_signal, meas_signal, samples):
        """Panel: Análisis espectral del ruido"""
        noise = meas_signal - ref_signal

        if len(noise) >= 64:  # Mínimo para FFT decente
            try:
                # Calcular FFT del ruido
                fft_noise = np.fft.fft(noise)
                freqs = np.fft.fftfreq(len(noise))

                # Solo frecuencias positivas
                pos_mask = freqs > 0
                freqs_pos = freqs[pos_mask]
                fft_magnitude = np.abs(fft_noise[pos_mask])

                # Convertir a dB
                fft_db = 20 * np.log10(fft_magnitude / np.max(fft_magnitude))

                # Plot espectro
                ax.plot(freqs_pos[:len(freqs_pos)//2], fft_db[:len(fft_db)//2],
                       'purple', linewidth=1.5, alpha=0.8)

                ax.set_xlabel('Frecuencia\n(relativa)', fontsize=8)
                ax.set_ylabel('Magnitud (dB)', fontsize=8)
                ax.set_title('Espectro\ndel Ruido', fontsize=9, fontweight='bold')
                ax.grid(True, alpha=0.3)
                ax.tick_params(labelsize=7)

            except:
                ax.text(0.5, 0.5, 'Error en\nanálisis espectral', ha='center', va='center', transform=ax.transAxes)
                ax.set_title('Espectro\ndel Ruido')
                ax.axis('off')

    def _plot_signal_quality_metrics(self, ax, ref_signal, meas_signal, samples):
        """Panel: Métricas de calidad de señal"""
        times, snr = self.calculate_snr_sliding(ref_signal, meas_signal, samples, window_size=25, step=5)

        if snr:
            # Calcular métricas de calidad
            quality_metrics = {
                'SNR Promedio': np.mean(snr),
                'SNR Std': np.std(snr),
                'SNR Min': np.min(snr),
                'SNR Max': np.max(snr),
                'Estabilidad': 1 / (np.std(snr) / abs(np.mean(snr))) if np.mean(snr) != 0 else 0,
                'Puntos': len(snr)
            }

            # Crear tabla
            ax.axis('tight')
            ax.axis('off')

            table_data = [[f'{val:.2f}' if isinstance(val, (int, float)) and val < 1000 else f'{val:.0f}'
                          for val in quality_metrics.values()]]
            table = ax.table(cellText=table_data,
                           colLabels=list(quality_metrics.keys()),
                           cellLoc='center',
                           loc='center',
                           colColours=['lightgreen'] * len(quality_metrics))

            table.auto_set_font_size(False)
            table.set_fontsize(6)
            table.scale(1, 1.0)

        ax.set_title('Métricas de\nCalidad SNR', fontsize=9, fontweight='bold')

    def _plot_snr_trends(self, ax, ref_signal, meas_signal, samples):
        """Panel: Análisis de tendencias en SNR"""
        times, snr = self.calculate_snr_sliding(ref_signal, meas_signal, samples, window_size=30, step=5)

        if snr and len(snr) > 5:
            # Convertir a arrays de numpy para operaciones matemáticas
            times = np.array(times)
            snr = np.array(snr)
            
            # Tendencia lineal
            try:
                from scipy import stats
                slope, intercept, r_value, p_value, std_err = stats.linregress(times, snr)

                ax.scatter(times, snr, alpha=0.6, s=15, color='blue', label='SNR')
                ax.plot(times, intercept + slope * times, 'r-', linewidth=2,
                       label=f'Tendencia\n(r={r_value:.3f})')

                # Estadísticas de tendencia
                trend_text = f'Pendiente: {slope:.3f} dB/muestra\nr: {r_value:.3f}\np: {p_value:.3f}'
                ax.text(0.02, 0.98, trend_text, transform=ax.transAxes,
                       verticalalignment='top', fontsize=7,
                       bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.8))

            except ImportError:
                ax.scatter(times, snr, alpha=0.6, s=15, color='blue', label='SNR')

            ax.set_xlabel('Muestras', fontsize=8)
            ax.set_ylabel('SNR (dB)', fontsize=8)
            ax.set_title('Tendencias\nSNR', fontsize=9, fontweight='bold')
            ax.legend(fontsize=6)
            ax.grid(True, alpha=0.3)
            ax.tick_params(labelsize=7)

        ax.set_xlabel('Ventana', fontsize=8)
        ax.set_ylabel('SNR (dB)', fontsize=8)
        ax.set_title('Raw vs\nFiltrado', fontsize=9, fontweight='bold')
        ax.grid(True, alpha=0.3)
        ax.tick_params(labelsize=7)

    def _plot_snr_summary_stats(self, ax, ref_signal, meas_signal, samples):
        """Panel: Resumen estadístico completo del SNR"""
        times, snr = self.calculate_snr_sliding(ref_signal, meas_signal, samples, window_size=25, step=5)

        if snr:
            # Calcular estadísticas completas
            stats_summary = {
                'Media': np.mean(snr),
                'Mediana': np.median(snr),
                'Std': np.std(snr),
                'Min': np.min(snr),
                'Max': np.max(snr),
                'P25': np.percentile(snr, 25),
                'P75': np.percentile(snr, 75),
                'CV': np.std(snr) / abs(np.mean(snr)) if np.mean(snr) != 0 else 0
            }

            # Crear tabla
            ax.axis('tight')
            ax.axis('off')

            table_data = [[f'{val:.2f}' for val in stats_summary.values()]]
            table = ax.table(cellText=table_data,
                           colLabels=list(stats_summary.keys()),
                           cellLoc='center',
                           loc='center',
                           colColours=['lightyellow'] * len(stats_summary))

            table.auto_set_font_size(False)
            table.set_fontsize(6)
            table.scale(1, 1.0)

        ax.set_title('Resumen\nEstadístico SNR', fontsize=9, fontweight='bold')

    def _plot_snr_variability(self, ax, ref_signal, meas_signal, samples):
        """Panel: Análisis de variabilidad del SNR"""
        times, snr = self.calculate_snr_sliding(ref_signal, meas_signal, samples, window_size=25, step=5)

        if snr and len(snr) > 10:
            snr_array = np.array(snr)

            # Calcular métricas de variabilidad
            snr_std = np.std(snr_array)
            snr_var = np.var(snr_array)
            snr_range = np.ptp(snr_array)
            snr_iqr = np.subtract(*np.percentile(snr_array, [75, 25]))

            # Crear box plot de SNR
            bp = ax.boxplot(snr_array, patch_artist=True,
                           boxprops=dict(facecolor='lightblue', alpha=0.7),
                           medianprops=dict(color='red', linewidth=2),
                           whiskerprops=dict(color='blue', linewidth=1.5),
                           capprops=dict(color='blue', linewidth=1.5))

            # Añadir puntos individuales
            ax.scatter(np.ones(len(snr_array)), snr_array, alpha=0.3, s=10, color='blue')

            # Estadísticas de texto
            stats_text = f'Std: {snr_std:.2f} dB\nVar: {snr_var:.2f} dB²\nIQR: {snr_iqr:.2f} dB\nRango: {snr_range:.2f} dB'
            ax.text(0.02, 0.98, stats_text, transform=ax.transAxes,
                   verticalalignment='top', fontsize=7,
                   bbox=dict(boxstyle='round', facecolor='lightyellow', alpha=0.8))

            ax.set_xticklabels(['SNR'])
            ax.set_ylabel('SNR (dB)', fontsize=8)
            ax.set_title('Variabilidad\ndel SNR', fontsize=9, fontweight='bold')
            ax.grid(True, alpha=0.3)
            ax.tick_params(labelsize=7)

    def _plot_snr_correlation_matrix(self, ax, ref_signal, meas_signal, samples):
        """Panel: Matriz de correlación de métricas SNR"""
        times, snr = self.calculate_snr_sliding(ref_signal, meas_signal, samples, window_size=20, step=5)

        if snr and len(snr) > 10:
            # Crear métricas relacionadas con SNR
            metrics_data = {
                'SNR': snr,
                'Amplitud': [np.max(ref_signal[i:i+20]) - np.min(ref_signal[i:i+20])
                           for i in range(0, len(ref_signal) - 20 + 1, 5)][:len(snr)],
                'Ruido_RMS': [np.sqrt(np.mean((meas_signal[i:i+20] - ref_signal[i:i+20])**2))
                            for i in range(0, len(ref_signal) - 20 + 1, 5)][:len(snr)],
                'Estabilidad': [1 / (np.std(ref_signal[i:i+20]) / abs(np.mean(ref_signal[i:i+20])) + 1e-10)
                              for i in range(0, len(ref_signal) - 20 + 1, 5)][:len(snr)]
            }

            # Ajustar longitudes
            min_len = min(len(v) for v in metrics_data.values())
            for key in metrics_data:
                metrics_data[key] = metrics_data[key][:min_len]

            # Calcular matriz de correlación
            df_metrics = pd.DataFrame(metrics_data)
            corr_matrix = df_metrics.corr()

            # Plot heatmap
            im = ax.imshow(corr_matrix, cmap='RdYlBu_r', aspect='auto', vmin=-1, vmax=1)

            # Etiquetas
            ax.set_xticks(range(len(corr_matrix.columns)))
            ax.set_yticks(range(len(corr_matrix.columns)))
            ax.set_xticklabels(corr_matrix.columns, rotation=45, ha='right', fontsize=7)
            ax.set_yticklabels(corr_matrix.columns, fontsize=7)

            # Añadir valores
            for i in range(len(corr_matrix.columns)):
                for j in range(len(corr_matrix.columns)):
                    val = corr_matrix.iloc[i, j]
                    ax.text(j, i, f'{val:.2f}', ha='center', va='center',
                           fontsize=6, fontweight='bold',
                           color='white' if abs(val) > 0.5 else 'black')

            ax.set_title('Correlación\nde Métricas', fontsize=9, fontweight='bold')

            # Colorbar pequeño
            from mpl_toolkits.axes_grid1 import make_axes_locatable
            divider = make_axes_locatable(ax)
            cax = divider.append_axes("right", size="20%", pad=0.1)
            plt.colorbar(im, cax=cax)
            cax.tick_params(labelsize=6)

    def clear_plots(self):
        """Limpiar todas las gráficas"""
        # Limpiar plots de visualización
        for widget in self.viz_plot_frame.winfo_children():
            widget.destroy()

        # Cerrar figuras
        for fig in self.plot_figures:
            plt.close(fig)

        self.plot_figures.clear()
        self.plot_canvases.clear()

    # Métodos de exportación
    def export_data(self, format_type):
        """Exportar datos en diferentes formatos"""
        if self.csv_data is None:
            messagebox.showwarning("Advertencia", "Carga los datos CSV primero")
            return

        try:
            base_name = os.path.splitext(os.path.basename(self.current_csv_file.get()))[0]

            if format_type == 'csv':
                file_path = filedialog.asksaveasfilename(
                    defaultextension=".csv",
                    filetypes=[("Archivos CSV", "*.csv")],
                    initialfile=f"{base_name}_export.csv"
                )
                if file_path:
                    self.csv_data.to_csv(file_path, index=False)

            elif format_type == 'xlsx':
                file_path = filedialog.asksaveasfilename(
                    defaultextension=".xlsx",
                    filetypes=[("Archivos Excel", "*.xlsx")],
                    initialfile=f"{base_name}_export.xlsx"
                )
                if file_path:
                    self.csv_data.to_excel(file_path, index=False, engine='openpyxl')

            elif format_type == 'json':
                file_path = filedialog.asksaveasfilename(
                    defaultextension=".json",
                    filetypes=[("Archivos JSON", "*.json")],
                    initialfile=f"{base_name}_export.json"
                )
                if file_path:
                    self.csv_data.to_json(file_path, orient='records', indent=2)

            elif format_type == 'parquet':
                file_path = filedialog.asksaveasfilename(
                    defaultextension=".parquet",
                    filetypes=[("Archivos Parquet", "*.parquet")],
                    initialfile=f"{base_name}_export.parquet"
                )
                if file_path:
                    self.csv_data.to_parquet(file_path, index=False)

            self.export_progress.set(f"Datos exportados exitosamente en formato {format_type.upper()}")
            self.log_message(f"Datos exportados en formato {format_type.upper()}")

        except Exception as e:
            messagebox.showerror("Error", f"Error exportando datos: {e}")
            self.logger.error(f"Error exporting data: {e}")

    # Métodos para análisis estadístico avanzado
    def update_analysis_controls(self):
        """Actualizar los controles específicos según el tipo de análisis seleccionado"""
        # Limpiar controles anteriores
        for widget in self.analysis_controls_frame.winfo_children():
            widget.destroy()

        analysis_type = self.analysis_type.get()

        if analysis_type in ["correlation", "histogram", "spectrum", "trend"]:
            # Controles para análisis básicos
            ttk.Label(self.analysis_controls_frame, text="Variable a analizar:",
                     font=('Arial', 9)).grid(row=0, column=0, sticky=tk.W, pady=2)

            # Obtener variables disponibles
            available_vars = []
            if self.csv_data is not None:
                available_vars = [col for col in self.csv_data.columns if col != 'Sample']

            self.analysis_signal_1_combo = ttk.Combobox(self.analysis_controls_frame,
                                                       textvariable=self.analysis_signal_1,
                                                       values=available_vars,
                                                       state="readonly", width=20)
            self.analysis_signal_1_combo.grid(row=0, column=1, sticky=tk.W, pady=2, padx=(10, 0))

        elif analysis_type in ["snr", "snr_filtered"]:
            # Controles para análisis SNR
            ttk.Label(self.analysis_controls_frame, text="Tamaño de ventana:",
                     font=('Arial', 9)).grid(row=0, column=0, sticky=tk.W, pady=2)
            ttk.Spinbox(self.analysis_controls_frame, from_=10, to=100, increment=5,
                        textvariable=self.analysis_window_size, width=10).grid(row=0, column=1, sticky=tk.W, pady=2, padx=(10, 0))

            ttk.Label(self.analysis_controls_frame, text="Paso:",
                     font=('Arial', 9)).grid(row=1, column=0, sticky=tk.W, pady=2)
            ttk.Spinbox(self.analysis_controls_frame, from_=1, to=20, increment=1,
                        textvariable=self.analysis_step_size, width=10).grid(row=1, column=1, sticky=tk.W, pady=2, padx=(10, 0))

        elif analysis_type == "histeresis":
            # Controles para análisis de histéresis
            ttk.Label(self.analysis_controls_frame, text="Mínimo de ciclos:",
                     font=('Arial', 9)).grid(row=0, column=0, sticky=tk.W, pady=2)
            ttk.Spinbox(self.analysis_controls_frame, from_=1, to=20, increment=1,
                        textvariable=self.analysis_min_cycles, width=10).grid(row=0, column=1, sticky=tk.W, pady=2, padx=(10, 0))

        # Información del análisis
        self.update_analysis_info()

    def update_analysis_info(self):
        """Actualizar la información del análisis seleccionado"""
        analysis_type = self.analysis_type.get()
        info_text = ""

        if analysis_type == "correlation":
            info_text = """📊 ANÁLISIS DE CORRELACIÓN

                Este análisis examina las relaciones entre diferentes variables del sistema.

                • Muestra matrices de correlación
                • Identifica variables relacionadas
                • Ayuda a entender dependencias del sistema

                Requiere: Al menos 2 variables numéricas"""
        elif analysis_type == "histogram":
            info_text = """📈 ANÁLISIS DE HISTOGRAMAS

                Analiza la distribución de frecuencia de las variables.

                • Muestra distribución de probabilidad
                • Identifica valores atípicos
                • Evalúa la normalidad de los datos

                Requiere: Una variable numérica"""
        elif analysis_type == "spectrum":
            info_text = """🌊 ANÁLISIS ESPECTRAL

                Examina las componentes de frecuencia de las señales.

                • Análisis FFT de las señales
                • Identifica frecuencias dominantes
                • Detecta ruido y patrones periódicos

                Requiere: Una señal temporal"""
        elif analysis_type == "trend":
            info_text = """📈 ANÁLISIS DE TENDENCIAS

                Evalúa cambios temporales en las variables.

                • Análisis de regresión lineal
                • Detección de tendencias
                • Evaluación de estabilidad temporal

                Requiere: Una variable con componente temporal"""
        elif analysis_type == "snr":
            info_text = """📡 ANÁLISIS SNR (RAW)

                Mide la relación señal-ruido usando datos sin filtrar.

                • Comparación TIVA Raw vs Keithley
                • Análisis temporal del SNR
                • Evaluación de calidad de señal

                Requiere: Columnas 'TIVA Voltage (V)' y 'KEITHLEY Voltage (V)'"""

        elif analysis_type == "histeresis":
            info_text = """🔄 ANÁLISIS DE HISTÉRESIS

                Analiza el comportamiento en ciclos de subida/bajada.

                • Comparación Raw vs Filtrado
                • Medición de histéresis por ciclo
                • Evaluación de estabilidad del sistema

                Requiere: Datos cíclicos con setpoint y respuesta"""
        elif analysis_type == "cycle_average":
            info_text = """🔁 ANÁLISIS DE CICLOS PROMEDIO

                Procesa datos cíclicos para obtener promedios.

                • Promedio de múltiples ciclos
                • Reducción de ruido
                • Análisis de comportamiento repetitivo

                Requiere: Datos con ciclos identificables"""
        elif analysis_type == "whitestone_bridge":
            info_text = """🌉 ANÁLISIS PUENTE WHEATSTONE

                Análisis específico del puente de medición.

                • Balance del puente
                • Sensibilidad y linealidad
                • Análisis de componentes AC/DC

                Requiere: Datos del puente Wheatstone"""
        elif analysis_type == "presion":
            info_text = """💨 ANÁLISIS DE PRESIÓN

                Análisis del sistema de control de presión.

                • Respuesta del sistema
                • Control PID de presión
                • Correlación presión-temperatura

                Requiere: Datos de presión y temperatura"""
        elif analysis_type == "estadisticas":
            info_text = """📊 ESTADÍSTICAS DESCRIPTIVAS

                Análisis estadístico completo de todas las variables.

                • Estadísticas descriptivas
                • Distribuciones y outliers
                • Análisis de normalidad
                • Correlaciones temporales

                Requiere: Múltiples variables numéricas"""

        self.analysis_info_text.config(state=tk.NORMAL)
        self.analysis_info_text.delete(1.0, tk.END)
        self.analysis_info_text.insert(tk.END, info_text)
        self.analysis_info_text.config(state=tk.DISABLED)

    def get_current_analysis_plot_frame(self):
        """Obtener el frame de plotting para el análisis actual"""
        analysis_type = self.analysis_type.get()
        if analysis_type in self.analysis_plot_frames:
            return self.analysis_plot_frames[analysis_type]
        else:
            # Fallback al frame general (para compatibilidad)
            return getattr(self, 'analysis_plot_frame', None)

    def create_analysis_canvas(self, fig, analysis_type=None):
        """Crear canvas para análisis en la pestaña correspondiente"""
        if analysis_type is None:
            analysis_type = self.analysis_type.get()

        plot_frame = self.get_current_analysis_plot_frame()
        if plot_frame:
            canvas = FigureCanvasTkAgg(fig, master=plot_frame)
            canvas.draw()
            canvas.get_tk_widget().pack(fill=tk.BOTH, expand=False)

            from matplotlib.backends.backend_tkagg import NavigationToolbar2Tk
            toolbar = NavigationToolbar2Tk(canvas, plot_frame)
            toolbar.update()
            toolbar.pack(side=tk.BOTTOM, fill=tk.X)

            # Almacenar figuras por tipo de análisis
            figures_list = self.get_analysis_figures_list(analysis_type)
            figures_list.append(fig)

            return canvas
        return None

    def get_analysis_figures_list(self, analysis_type):
        """Obtener la lista de figuras para un tipo de análisis específico"""
        attr_name = f'{analysis_type}_figures'
        if not hasattr(self, attr_name):
            setattr(self, attr_name, [])
        return getattr(self, attr_name)

    def run_selected_analysis(self):
        """Ejecutar el análisis seleccionado"""
        if self.csv_data is None:
            messagebox.showwarning("Advertencia", "No hay datos CSV cargados para analizar")
            return

        analysis_type = self.analysis_type.get()

        try:
            # Limpiar resultados anteriores para este análisis
            if analysis_type in self.analysis_results:
                del self.analysis_results[analysis_type]

            # Ejecutar el análisis correspondiente
            if analysis_type == "histeresis":
                self.run_histeresis_analysis()
            elif analysis_type == "correlation":
                self.run_correlation_analysis()
            elif analysis_type == "histogram":
                self.run_histogram_analysis()
            elif analysis_type == "spectrum":
                self.run_spectrum_analysis()
            elif analysis_type == "trend":
                self.run_trend_analysis()
            elif analysis_type == "snr":
                self.run_snr_analysis(raw=True)
            elif analysis_type == "snr_filtered":
                self.run_snr_analysis(raw=False)
            elif analysis_type == "cycle_average":
                self.run_cycle_average_analysis()
            elif analysis_type == "whitestone_bridge":
                self.run_whitestone_bridge_analysis()
            elif analysis_type == "presion":
                self.run_presion_analysis()
            elif analysis_type == "estadisticas":
                self.run_estadisticas_analysis()
            else:
                messagebox.showerror("Error", f"Tipo de análisis '{analysis_type}' no implementado")
                return

            self.log_message(f"Análisis '{analysis_type}' completado exitosamente")
        except Exception as e:
            messagebox.showerror("Error", f"Error al ejecutar análisis: {str(e)}")
            self.log_message(f"Error en análisis '{analysis_type}': {e}")

    def clear_current_analysis_tab(self):
        """Limpiar la pestaña actual de análisis"""
        analysis_type = self.analysis_type.get()

        if analysis_type in self.analysis_plot_frames:
            plot_frame = self.analysis_plot_frames[analysis_type]

            # Limpiar widgets
            for widget in plot_frame.winfo_children():
                widget.destroy()

            # Cerrar figuras
            figures_list = self.get_analysis_figures_list(analysis_type)
            for fig in figures_list:
                plt.close(fig)
            figures_list.clear()

            # Limpiar resultados
            if analysis_type in self.analysis_results:
                del self.analysis_results[analysis_type]

            # Limpiar información
            self.analysis_info_text.delete(1.0, tk.END)

            self.log_message(f"Pestaña de análisis '{analysis_type}' limpiada")

    def run_histeresis_analysis(self):
        """Ejecutar análisis de histéresis"""
        # Reutilizar la lógica existente de plot_histeresis_analysis
        # pero adaptada para el nuevo sistema de pestañas

        # Verificar que tenemos las columnas necesarias
        required_cols = ['Ciclo', 'Fase', 'Setpoint Enviado (kPA)', 'TIVA Voltage (V)', 'KEITHLEY Voltage (V)']
        missing_cols = [col for col in required_cols if col not in self.csv_data.columns]

        if missing_cols:
            self.analysis_info_text.insert(tk.END, f'Columnas requeridas faltantes: {", ".join(missing_cols)}\n')
            self.analysis_info_text.insert(tk.END, 'Se necesitan: Ciclo, Fase, Setpoint Enviado (kPA), KEITHLEY Voltage (V)\n')
            return

        # Filtrar datos válidos
        data = self.csv_data[required_cols].dropna()

        if len(data) == 0:
            self.analysis_info_text.insert(tk.END, 'No hay datos válidos para análisis de histéresis\n')
            return

        # Obtener ciclos únicos
        ciclos_unicos = sorted(data['Ciclo'].unique())

        if len(ciclos_unicos) == 0:
            self.analysis_info_text.insert(tk.END, 'No se encontraron ciclos en los datos\n')
            return

        # Inicializar resultados
        results = {
            'cycles': [],
            'global_summary': {},
            'export_data': []
        }

        # Crear figura
        n_ciclos = len(ciclos_unicos)
        fig, axes = plt.subplots(n_ciclos, 1, figsize=(12, 6*n_ciclos))
        if n_ciclos == 1:
            axes = [axes]
        fig.suptitle('Análisis de Histéresis - Error por Ciclo', fontsize=14)

        total_histeresis_area = 0
        cycle_areas = []
        cycle_areas_keithley = []
        total_histeresis_area_keithley = 0

        for i, ciclo in enumerate(ciclos_unicos):
            cycle_data = data[data['Ciclo'] == ciclo]

            # Obtener setpoints únicos ordenados
            setpoints_unicos = sorted(cycle_data['Setpoint Enviado (kPA)'].unique())

            # Calcular promedios por fase y setpoint
            subida_data_Tiva_Voltaje = []
            subida_data_KEITHLEY_Voltaje = []
            
            bajada_data_Tiva_Voltaje = []
            bajada_data_KEITHLEY_Voltaje = []

            for setpoint in setpoints_unicos:
                setpoint_data = cycle_data[cycle_data['Setpoint Enviado (kPA)'] == setpoint]

                # Promedio subida
                subida_vals = setpoint_data[setpoint_data['Fase'] == 'subida']['TIVA Voltage (V)']
                if len(subida_vals) > 0:
                    subida_avg = np.mean(subida_vals)
                    subida_data_Tiva_Voltaje.append((setpoint, subida_avg))

                subida_vals = setpoint_data[setpoint_data['Fase'] == 'subida' ]['KEITHLEY Voltage (V)']
                if len(subida_vals) > 0:
                    subida_avg = np.mean(subida_vals)
                    subida_data_KEITHLEY_Voltaje.append((setpoint, subida_avg))

                # Promedio bajada
                bajada_vals = setpoint_data[setpoint_data['Fase'] == 'bajada']['TIVA Voltage (V)']
                if len(bajada_vals) > 0:
                    bajada_avg = np.mean(bajada_vals)
                    bajada_data_Tiva_Voltaje.append((setpoint, bajada_avg))

                bajada_vals = setpoint_data[setpoint_data['Fase'] == 'bajada']['KEITHLEY Voltage (V)']
                if len(bajada_vals) > 0:
                    bajada_avg = np.mean(bajada_vals)
                    bajada_data_KEITHLEY_Voltaje.append((setpoint, bajada_avg))

            cycle_info = {
                'ciclo': int(ciclo),
                'subida_data_Tiva_Voltaje': subida_data_Tiva_Voltaje.copy(),
                'subida_data_KEITHLEY_Voltaje': subida_data_KEITHLEY_Voltaje.copy(),
                'bajada_data_Tiva_Voltaje': bajada_data_Tiva_Voltaje.copy(),
                'bajada_data_KEITHLEY_Voltaje': bajada_data_KEITHLEY_Voltaje.copy(),
                'setpoints_comunes': [],
                'hist_error': [],
                'cycle_area': 0.0,
                'valid_data': False
            }

            if len(subida_data_Tiva_Voltaje) > 0 and len(bajada_data_Tiva_Voltaje) > 0 and len(subida_data_KEITHLEY_Voltaje) > 0 and len(bajada_data_KEITHLEY_Voltaje):
                # Crear arrays para interpolación
                subida_setpoints = np.array([x[0] for x in subida_data_Tiva_Voltaje])

                subida_voltajes_tiva = np.array([x[1] for x in subida_data_Tiva_Voltaje])
                subida_voltajes_keithley = np.array([x[1] for x in subida_data_KEITHLEY_Voltaje])

                bajada_setpoints = np.array([x[0] for x in bajada_data_Tiva_Voltaje])

                bajada_voltajes_tiva = np.array([x[1] for x in bajada_data_Tiva_Voltaje])
                bajada_voltajes_keithley = np.array([x[1] for x in bajada_data_KEITHLEY_Voltaje])

                # Encontrar setpoints comunes
                setpoints_comunes = np.intersect1d(subida_setpoints, bajada_setpoints)
                setpoints_comunes = np.sort(setpoints_comunes)

                if len(setpoints_comunes) > 1:
                    # Interpolar valores para setpoints comunes
                    subida_interp = np.interp(setpoints_comunes, subida_setpoints, subida_voltajes_tiva)
                    subida_interp_keithley = np.interp(setpoints_comunes, subida_setpoints, subida_voltajes_keithley)

                    bajada_interp = np.interp(setpoints_comunes, bajada_setpoints, bajada_voltajes_tiva)
                    bajada_interp_keithley = np.interp(setpoints_comunes, bajada_setpoints, bajada_voltajes_keithley)

                    # Calcular error de histéresis
                    hist_error = subida_interp - bajada_interp
                    hist_error_keithley = subida_interp_keithley - bajada_interp_keithley


                    # Calcular área del error de histéresis usando integración trapezoidal
                    cycle_area = np.trapz(np.abs(hist_error), setpoints_comunes)
                    cycle_area_keithley = np.trapz(np.abs(hist_error_keithley), setpoints_comunes)
                    
                    cycle_areas.append(cycle_area)
                    cycle_areas_keithley.append(cycle_area_keithley)
                    
                    total_histeresis_area += cycle_area
                    total_histeresis_area_keithley += cycle_area_keithley

                    # Almacenar datos para exportación
                    cycle_info.update({
                        'setpoints_comunes': setpoints_comunes.tolist(),
                        'subida_interp': subida_interp.tolist(),
                        'subida_interp_keithley': subida_interp_keithley.tolist(),
                        'bajada_interp': bajada_interp.tolist(),
                        'bajada_interp_keithley': bajada_interp_keithley.tolist(),
                        'hist_error': hist_error.tolist(),
                        'hist_error_keithley': hist_error_keithley.tolist(),
                        'cycle_area': float(cycle_area),
                        'cycle_area_keithley': float(cycle_area_keithley),
                        'valid_data': True
                    })

                    # Graficar
                    axes[i].plot(setpoints_comunes, subida_interp, 'b-o', label='Subida', linewidth=2, markersize=4)
                    axes[i].plot(setpoints_comunes, bajada_interp, 'r-s', label='Bajada', linewidth=2, markersize=4)
                    axes[i].plot(setpoints_comunes, hist_error, 'g--', label='Error de Histéresis', linewidth=2)

                    # Rellenar área del error
                    axes[i].fill_between(setpoints_comunes, 0, hist_error, alpha=0.3, color='green', label=f'Área = {cycle_area:.6f}')

                    axes[i].set_xlabel('Setpoint de Presión (kPA)')
                    axes[i].set_ylabel('KEITHLEY Voltage (V) / Error (V)')
                    axes[i].set_title(f'Ciclo {int(ciclo)} - Área de Histéresis = {cycle_area:.6f} V·kPa')
                    axes[i].legend()
                    axes[i].grid(True, alpha=0.3)

                    # Añadir valores en los puntos
                    for j, (sp, err) in enumerate(zip(setpoints_comunes, hist_error)):
                        axes[i].annotate(f'{err:.6f}', (sp, err), textcoords="offset points", xytext=(0,10), ha='center', fontsize=8)
                else:
                    axes[i].text(0.5, 0.5, f'Ciclo {int(ciclo)}: No hay suficientes puntos comunes para análisis',
                               transform=axes[i].transAxes, ha='center', va='center', fontsize=12)
                    axes[i].set_title(f'Ciclo {int(ciclo)} - Datos Insuficientes')
            else:
                axes[i].text(0.5, 0.5, f'Ciclo {int(ciclo)}: Faltan datos de subida o bajada',
                           transform=axes[i].transAxes, ha='center', va='center', fontsize=12)
                axes[i].set_title(f'Ciclo {int(ciclo)} - Datos Incompletos')

            results['cycles'].append(cycle_info)

        # Almacenar resultados globales
        # punto decimal de .2f a float para compatibilidad JSON
        results['global_summary'] = {
            'total_histeresis_area': f"{total_histeresis_area:.6f}",
            'total_histeresis_area_keithley': f"{total_histeresis_area_keithley:.6f}",
            'num_cycles_analyzed': len(cycle_areas),
            'average_area_per_cycle': f"{float(total_histeresis_area / len(cycle_areas)):.6f}" if cycle_areas else "0.0",
            'average_area_per_cycle_keithley': f"{float(total_histeresis_area_keithley / len(cycle_areas_keithley)):.6f}" if cycle_areas_keithley else "0.0",
            'cycle_areas': [f"{float(area):.6f}" for area in cycle_areas],
            'cycle_areas_keithley': [f"{float(area):.6f}" for area in cycle_areas_keithley]
        }

        # Preparar datos para exportación
        setpoint_summary = {}  # Para calcular promedios generales

        for cycle in results['cycles']:
            # Exportar promedios de subida para cada setpoint
            for setpoint, avg_voltage in cycle['subida_data_Tiva_Voltaje']:
                results['export_data'].append({
                    'Ciclo': cycle['ciclo'],
                    'Fase': 'Subida',
                    'Setpoint (kPA)': setpoint,
                    'TIVA Raw (V)': f"{avg_voltage:.6f}",
                    'Tipo': 'TIVA Raw'
                })

            for setpoint, avg_voltage in cycle['subida_data_KEITHLEY_Voltaje']:
                results['export_data'].append({
                    'Ciclo': cycle['ciclo'],
                    'Fase': 'Subida',
                    'Setpoint (kPA)': setpoint,
                    'KEITHLEY (V)': f"{avg_voltage:.6f}",
                    'Tipo': 'KEITHLEY'
                })

            # Exportar promedios de bajada para cada setpoint
            for setpoint, avg_voltage in cycle['bajada_data_Tiva_Voltaje']:
                results['export_data'].append({
                    'Ciclo': cycle['ciclo'],
                    'Fase': 'Bajada',
                    'Setpoint (kPA)': setpoint,
                    'TIVA Raw (V)': f"{avg_voltage:.6f}",
                    'Tipo': 'TIVA Raw'
                })

            for setpoint, avg_voltage in cycle['bajada_data_KEITHLEY_Voltaje']:
                results['export_data'].append({
                    'Ciclo': cycle['ciclo'],
                    'Fase': 'Bajada',
                    'Setpoint (kPA)': setpoint,
                    'KEITHLEY (V)': f"{avg_voltage:.6f}",
                    'Tipo': 'KEITHLEY'
                })

            # Exportar datos de histéresis (interpolados) si hay datos válidos
            if cycle['valid_data']:
                for sp, sub, sub_K, baj, baj_K, err in zip(cycle['setpoints_comunes'], cycle['subida_interp'], cycle['subida_interp_keithley'], cycle['bajada_interp'], cycle['bajada_interp_keithley'], cycle['hist_error']):
                    results['export_data'].append({
                        'Ciclo': cycle['ciclo'],
                        'Fase': 'Histéresis',
                        'Setpoint (kPA)': sp,
                        'Subida (V)': f"{sub:.6f}",
                        'Subida KEITHLEY (V)': f"{sub_K:.6f}",
                        'Bajada (V)': f"{baj:.6f}",
                        'Bajada KEITHLEY (V)': f"{baj_K:.6f}",
                        'Error Histéresis (V)': f"{err:.6f}",
                        'Tipo': 'Histéresis'
                    })

                    # Acumular para promedio general
                    if sp not in setpoint_summary:
                        setpoint_summary[sp] = {'subida': [], 'subida_KEITHLEY': [], 'bajada': [], 'bajada_KEITHLEY': [], 'error': []}
                    setpoint_summary[sp]['subida'].append(sub)
                    setpoint_summary[sp]['subida_KEITHLEY'].append(sub_K)
                    setpoint_summary[sp]['bajada'].append(baj)
                    setpoint_summary[sp]['bajada_KEITHLEY'].append(baj_K)
                    setpoint_summary[sp]['error'].append(err)

        # Añadir promedio general si hay más de 1 ciclo
        if len(ciclos_unicos) > 1 and setpoint_summary:
            for sp, data in setpoint_summary.items():
                if len(data['subida']) > 1:  # Solo si hay datos de múltiples ciclos
                    avg_sub = np.mean(data['subida'])
                    avg_sub_keithley = np.mean(data['subida_KEITHLEY'])
                    avg_baj = np.mean(data['bajada'])
                    avg_baj_keithley = np.mean(data['bajada_KEITHLEY'])
                    avg_err = np.mean(data['error'])
                    results['export_data'].append({
                        'Ciclo': 'Promedio General',
                        'Fase': 'Histéresis',
                        'Setpoint (kPA)': sp,
                        'Subida (V)': f"{avg_sub:.6f}",
                        'Subida KEITHLEY (V)': f"{avg_sub_keithley:.6f}",
                        'Bajada (V)': f"{avg_baj:.6f}",
                        'Bajada KEITHLEY (V)': f"{avg_baj_keithley:.6f}",
                        'Error Histéresis (V)': f"{avg_err:.6f}",
                        'Tipo': 'Histéresis'
                    })

        # Almacenar resultados
        self.analysis_results['histeresis'] = results

        # Añadir resumen global
        if cycle_areas:
            summary_text = f'Área Total de Histéresis (TIVA): {total_histeresis_area:.6f} V·kPa\n'
            summary_text += f'Área Total de Histéresis (KEITHLEY): {total_histeresis_area_keithley:.6f} V·kPa\n'
            summary_text += f'Número de Ciclos Analizados: {len(cycle_areas)}\n'
            summary_text += f'Área Promedio por Ciclo (TIVA): {total_histeresis_area/len(cycle_areas):.6f} V·kPa'

            # Añadir texto en la figura
            fig.text(0.02, 0.98, summary_text, transform=fig.transFigure,
                    verticalalignment='top', fontsize=10,
                    bbox=dict(boxstyle='round', facecolor='lightblue', alpha=0.8))

        plt.tight_layout(h_pad=0.3)

        # Mostrar en la pestaña correspondiente
        self.display_analysis_figure(fig, 'histeresis')

        # Mostrar información
        self.analysis_info_text.delete(1.0, tk.END)
        self.analysis_info_text.insert(tk.END, f"Análisis de Histéresis completado\n\n")
        self.analysis_info_text.insert(tk.END, f"Ciclos analizados: {len(cycle_areas)}\n")
        self.analysis_info_text.insert(tk.END, f"Área total de histéresis (TIVA): {total_histeresis_area:.6f} V·kPa\n")
        self.analysis_info_text.insert(tk.END, f"Área total de histéresis (KEITHLEY): {total_histeresis_area_keithley:.6f} V·kPa\n")
        if cycle_areas:
            self.analysis_info_text.insert(tk.END, f"Área promedio por ciclo (TIVA): {total_histeresis_area/len(cycle_areas):.6f} V·kPa\n")
        else:
            self.analysis_info_text.insert(tk.END, "No se pudieron calcular áreas\n")

    def display_analysis_figure(self, fig, analysis_type):
        """Mostrar figura en la pestaña correspondiente con scrollbar vertical y scrollbar horizontal"""
        if analysis_type not in self.analysis_plot_frames:
            return

        plot_frame = self.analysis_plot_frames[analysis_type]

        # Limpiar contenido anterior
        for widget in plot_frame.winfo_children():
            widget.destroy()

        # Crear frame contenedor con scrollbar vertical
        container_frame = ttk.Frame(plot_frame)
        container_frame.pack(fill=tk.BOTH, expand=True)

        # Crear canvas de tkinter para el scrollbar
        canvas = tk.Canvas(container_frame, bg='white', highlightthickness=0)
        scrollbar = ttk.Scrollbar(container_frame, orient=tk.VERTICAL, command=canvas.yview)
        scrollable_frame = ttk.Frame(canvas)

        scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )

        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        # Configurar scroll con mouse wheel
        def _on_mousewheel(event):
            canvas.yview_scroll(int(-1*(event.delta/120)), "units")

        # Configurar scroll horizontal
        def _on_mousewheel_horizontal(event):
            canvas.xview_scroll(int(-1*(event.delta/120)), "units")

        canvas.bind_all("<MouseWheel>", _on_mousewheel)
        canvas.bind_all("<Shift-MouseWheel>", _on_mousewheel_horizontal)

        # Crear canvas de matplotlib dentro del frame scrollable
        matplotlib_canvas = FigureCanvasTkAgg(fig, master=scrollable_frame)
        matplotlib_canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)

        # Añadir navegación de matplotlib
        from matplotlib.backends.backend_tkagg import NavigationToolbar2Tk
        toolbar = NavigationToolbar2Tk(matplotlib_canvas, scrollable_frame)
        toolbar.update()
        toolbar.pack(side=tk.BOTTOM, fill=tk.X)

        # Empaquetar los elementos
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        # Ajustar el tamaño del canvas cuando cambie el tamaño de la ventana
        def configure_canvas(event):
            canvas.configure(scrollregion=canvas.bbox("all"))

        scrollable_frame.bind("<Configure>", configure_canvas)

        # Almacenar referencia
        figures_list = self.get_analysis_figures_list(analysis_type)
        figures_list.append(fig)

        # Cambiar a la pestaña correspondiente
        for i, (tab_type, _) in enumerate([
            ('histeresis', '🔄 Análisis de Histéresis'),
            ('correlation', '📊 Análisis de Correlación'),
            ('histogram', '📈 Análisis de Histogramas'),
            ('spectrum', '🌊 Análisis Espectral'),
            ('trend', '📈 Análisis de Tendencias'),
            ('snr', '📡 Análisis SNR (Raw)'),
            ('cycle_average', '🔁 Análisis de Ciclos Promedio'),
            ('whitestone_bridge', '🌉 Análisis Puente Wheatstone'),
            ('presion', '💨 Análisis de Presión'),
            ('estadisticas', '📊 Estadísticas Descriptivas')
        ]):
            if tab_type == analysis_type:
                self.analysis_notebook.select(i)
                break

    def export_analysis_data(self, format_type):
        """Exportar datos del análisis actual"""
        analysis_type = self.analysis_type.get()

        if analysis_type not in self.analysis_results:
            messagebox.showwarning("Exportación", f"No hay datos de análisis '{analysis_type}' disponibles para exportar")
            return

        results = self.analysis_results[analysis_type]

        # Diálogo para seleccionar archivo
        filetypes = {
            'csv': [('CSV files', '*.csv'), ('All files', '*.*')],
            'xlsx': [('Excel files', '*.xlsx'), ('All files', '*.*')],
            'json': [('JSON files', '*.json'), ('All files', '*.*')]
        }

        filename = filedialog.asksaveasfilename(
            title=f"Exportar datos de análisis '{analysis_type}' como {format_type.upper()}",
            defaultextension=f".{format_type}",
            filetypes=filetypes[format_type]
        )

        if not filename:
            return

        try:
            if format_type == 'csv':
                self._export_analysis_csv(filename, results, analysis_type)
            elif format_type == 'xlsx':
                self._export_analysis_xlsx(filename, results, analysis_type)
            elif format_type == 'json':
                self._export_analysis_json(filename, results, analysis_type)

            messagebox.showinfo("Exportación Exitosa",
                              f"Datos de análisis '{analysis_type}' exportados correctamente a {filename}")

        except Exception as e:
            messagebox.showerror("Error de Exportación",
                               f"Error al exportar datos: {str(e)}")

    def _export_analysis_csv(self, filename, results, analysis_type):
        """Exportar datos de análisis a CSV"""
        with open(filename, 'w', newline='', encoding='utf-8') as csvfile:
            writer = csv.writer(csvfile)

            # Escribir metadatos
            writer.writerow(['ANÁLISIS', analysis_type.upper()])
            writer.writerow(['FECHA EXPORTACIÓN', datetime.now().strftime('%Y-%m-%d %H:%M:%S')])
            writer.writerow([])

            # Escribir resumen global si existe
            if 'global_summary' in results and results['global_summary']:
                writer.writerow(['RESUMEN GLOBAL'])
                writer.writerow(['Métrica', 'Valor'])
                for key, value in results['global_summary'].items():
                    writer.writerow([key, value])
                writer.writerow([])

            # Escribir datos específicos del análisis
            if analysis_type == 'histeresis' and 'export_data' in results:
                writer.writerow(['DATOS DE HISTÉRESIS - ANÁLISIS COMPLETO'])
                writer.writerow(['Este archivo contiene promedios por fase, datos interpolados de histéresis y promedios generales'])
                writer.writerow([])

                # Separar datos por tipo para mejor organización
                phase_averages = [row for row in results['export_data'] if row.get('Tipo') in ['TIVA Raw', 'KEITHLEY']]
                hysteresis_data = [row for row in results['export_data'] if row.get('Tipo') == 'Histéresis']

                # Exportar promedios por fase
                if phase_averages:
                    writer.writerow(['PROMEDIOS POR FASE Y SETPOINT'])
                    if phase_averages:
                        all_keys = set()
                        for row in phase_averages:
                            if isinstance(row, dict):
                                all_keys.update(row.keys())

                        header = sorted(list(all_keys))
                        writer.writerow(header)

                        for row in phase_averages:
                            if isinstance(row, dict):
                                writer.writerow([row.get(key, '') for key in header])
                    writer.writerow([])

                # Exportar datos de histéresis
                if hysteresis_data:
                    writer.writerow(['DATOS DE HISTÉRESIS (Interpolados)'])
                    if hysteresis_data:
                        all_keys = set()
                        for row in hysteresis_data:
                            if isinstance(row, dict):
                                all_keys.update(row.keys())

                        header = sorted(list(all_keys))
                        writer.writerow(header)

                        for row in hysteresis_data:
                            if isinstance(row, dict):
                                writer.writerow([row.get(key, '') for key in header])
                    writer.writerow([])

                writer.writerow(['FIN DEL ARCHIVO'])

            # Para otros análisis, escribir datos genéricos
            elif 'cycles' in results:
                for cycle in results['cycles']:
                    if cycle.get('valid_data', False):
                        writer.writerow([f'CICLO {cycle["ciclo"]}'])
                        # Escribir datos del ciclo según el tipo de análisis
                        if 'subida_data' in cycle:
                            writer.writerow(['FASE SUBIDA'])
                            writer.writerow(['Setpoint', 'Valor'])
                            for sp, val in cycle['subida_data']:
                                writer.writerow([sp, val])
                        if 'bajada_data' in cycle:
                            writer.writerow(['FASE BAJADA'])
                            writer.writerow(['Setpoint', 'Valor'])
                            for sp, val in cycle['bajada_data']:
                                writer.writerow([sp, val])
                        writer.writerow([])

    def _export_analysis_xlsx(self, filename, results, analysis_type):
        """Exportar datos de análisis a Excel"""
        with pd.ExcelWriter(filename, engine='openpyxl') as writer:
            # Metadatos
            metadata_df = pd.DataFrame({
                'Información': ['Análisis', 'Fecha Exportación'],
                'Valor': [analysis_type.upper(), datetime.now().strftime('%Y-%m-%d %H:%M:%S')]
            })
            metadata_df.to_excel(writer, sheet_name='Metadatos', index=False)

            # Resumen global
            if 'global_summary' in results and results['global_summary']:
                summary_df = pd.DataFrame(list(results['global_summary'].items()), columns=['Métrica', 'Valor'])
                summary_df.to_excel(writer, sheet_name='Resumen_Global', index=False)

            # Datos específicos
            if analysis_type == 'histeresis' and 'export_data' in results:
                # Separar datos por tipo para mejor organización
                phase_averages = [row for row in results['export_data'] if row.get('Tipo') in ['TIVA Raw', 'KEITHLEY']]
                hysteresis_data = [row for row in results['export_data'] if row.get('Tipo') == 'Histéresis']

                # Exportar promedios por fase en hoja separada
                if phase_averages:
                    phase_df = pd.DataFrame(phase_averages)
                    phase_df.to_excel(writer, sheet_name='Promedios_por_Fase', index=False)

                # Exportar datos de histéresis en hoja separada
                if hysteresis_data:
                    hist_df = pd.DataFrame(hysteresis_data)
                    hist_df.to_excel(writer, sheet_name='Datos_Histeresis', index=False)

            # Para otros análisis
            elif 'cycles' in results:
                for i, cycle in enumerate(results['cycles']):
                    if cycle.get('valid_data', False):
                        cycle_data = []
                        if 'subida_data' in cycle:
                            for sp, val in cycle['subida_data']:
                                cycle_data.append({'Fase': 'Subida', 'Setpoint': sp, 'Valor': val})
                        if 'bajada_data' in cycle:
                            for sp, val in cycle['bajada_data']:
                                cycle_data.append({'Fase': 'Bajada', 'Setpoint': sp, 'Valor': val})

                        if cycle_data:
                            cycle_df = pd.DataFrame(cycle_data)
                            sheet_name = f'Ciclo_{cycle["ciclo"]}'
                            cycle_df.to_excel(writer, sheet_name=sheet_name, index=False)

    def _export_analysis_json(self, filename, results, analysis_type):
        """Exportar datos de análisis a JSON"""
        # Preparar datos para JSON
        json_data = {
            'metadata': {
                'analysis_type': analysis_type,
                'export_timestamp': datetime.now().isoformat(),
                'description': f'Datos de análisis {analysis_type}'
            },
            'results': results
        }

        import json
        with open(filename, 'w', encoding='utf-8') as jsonfile:
            json.dump(json_data, jsonfile, indent=2, ensure_ascii=False)

    # Placeholder methods for other analysis types
    def run_correlation_analysis(self):
        """Placeholder for correlation analysis"""
        self.analysis_info_text.insert(tk.END, "Análisis de correlación no implementado aún\n")

    def run_histogram_analysis(self):
        """Ejecutar análisis comprehensivo de histogramas para todas las variables numéricas"""
        # Obtener variables numéricas disponibles
        available_vars = []
        var_labels = {}

        for col in self.csv_data.columns:
            if col != 'Timestamp' and self.csv_data[col].dtype in ['int64', 'float64']:
                # Verificar que tenga suficientes datos no nulos
                non_null_count = self.csv_data[col].notna().sum()
                if non_null_count >= 30:  # Mínimo 30 puntos para análisis estadístico
                    available_vars.append(col)
                    # Crear etiquetas más legibles
                    if 'Voltage' in col:
                        var_labels[col] = col.replace('Voltage', 'Voltaje')
                    elif 'Temp' in col:
                        var_labels[col] = col.replace('Temp', 'Temperatura')
                    elif 'Presion' in col:
                        var_labels[col] = col.replace('Presion', 'Presión')
                    elif 'Setpoint' in col:
                        var_labels[col] = col.replace('Setpoint', 'Setpoint')
                    else:
                        var_labels[col] = col

        if len(available_vars) == 0:
            self.analysis_info_text.insert(tk.END, "No hay variables numéricas con suficientes datos para análisis de histogramas\n")
            self.analysis_info_text.insert(tk.END, "Se requieren al menos 30 puntos de datos por variable\n")
            return

        # Crear figura comprehensiva con layout 3x3
        fig, axes = plt.subplots(3, 3, figsize=(18, 14), dpi=100)
        axes = axes.flatten()

        fig.suptitle('Análisis Comprehensivo de Histogramas', fontsize=16, fontweight='bold')

        # Panel 1: Histogramas individuales con ajuste normal
        ax1 = axes[0]
        self._plot_individual_histograms(ax1, available_vars, var_labels)

        # Panel 2: Diagramas de caja (box plots)
        ax2 = axes[1]
        self._plot_box_plots(ax2, available_vars, var_labels)

        # Panel 3: Análisis de calidad de datos
        ax3 = axes[2]
        self._plot_data_quality(ax3, available_vars)

        # Panel 4: Análisis de tendencias temporales
        ax4 = axes[3]
        self._plot_trend_analysis(ax4, available_vars[0] if available_vars else None)

        # Panel 5: Análisis de estabilidad
        ax5 = axes[4]
        self._plot_stability_analysis(ax5, available_vars[0] if available_vars else None)

        # Panel 6: Pruebas de normalidad
        ax6 = axes[5]
        self._plot_normality_tests(ax6, available_vars)

        # Panel 7: Análisis de outliers
        ax7 = axes[6]
        self._plot_outlier_analysis(ax7, available_vars[0] if available_vars else None)

        # Panel 8: Análisis de correlación temporal
        ax8 = axes[7]
        self._plot_time_correlation(ax8, available_vars)

        # Panel 9: Autocorrelación
        ax9 = axes[8]
        self._plot_autocorrelation(ax9, available_vars[0] if available_vars else None)

        plt.tight_layout(h_pad=0.3, w_pad=0.3)

        # Mostrar en la pestaña correspondiente
        self.display_analysis_figure(fig, 'histogram')

        # Calcular estadísticas globales para el resumen
        stats_summary = {}
        for var in available_vars:
            data = self.csv_data[var].dropna()
            if len(data) > 0:
                stats_summary[var] = {
                    'count': len(data),
                    'mean': float(data.mean()),
                    'std': float(data.std()),
                    'min': float(data.min()),
                    'max': float(data.max()),
                    'skewness': float(data.skew()),
                    'kurtosis': float(data.kurtosis())
                }

        # Almacenar resultados
        results = {
            'variables_analyzed': available_vars,
            'total_variables': len(available_vars),
            'statistics_summary': stats_summary,
            'global_summary': {
                'Variables Analizadas': len(available_vars),
                'Total de Observaciones': len(self.csv_data),
                'Variables con Datos Completos': sum(1 for var in available_vars if self.csv_data[var].notna().all()),
                'Variables con Datos Faltantes': sum(1 for var in available_vars if self.csv_data[var].isna().any())
            }
        }

        self.analysis_results['histogram'] = results

        # Actualizar información del análisis
        self.analysis_info_text.delete(1.0, tk.END)
        self.analysis_info_text.insert(tk.END, "Análisis de Histogramas completado exitosamente\n\n")
        self.analysis_info_text.insert(tk.END, f"Variables analizadas: {len(available_vars)}\n")
        for var in available_vars:
            self.analysis_info_text.insert(tk.END, f"• {var_labels.get(var, var)}\n")

        self.analysis_info_text.insert(tk.END, f"\nResumen estadístico:\n")
        for var, stats in stats_summary.items():
            self.analysis_info_text.insert(tk.END, f"\n{var_labels.get(var, var)}:\n")
            self.analysis_info_text.insert(tk.END, f"  Media: {stats['mean']:.4f}\n")
            self.analysis_info_text.insert(tk.END, f"  Desv. Est.: {stats['std']:.4f}\n")
            self.analysis_info_text.insert(tk.END, f"  Rango: [{stats['min']:.4f}, {stats['max']:.4f}]\n")
            self.analysis_info_text.insert(tk.END, f"  Asimetría: {stats['skewness']:.4f}\n")
            self.analysis_info_text.insert(tk.END, f"  Curtosis: {stats['kurtosis']:.4f}\n")

    def run_spectrum_analysis(self):
        """Placeholder for spectrum analysis"""
        self.analysis_info_text.insert(tk.END, "Análisis espectral no implementado aún\n")

    def run_trend_analysis(self):
        """Placeholder for trend analysis"""
        self.analysis_info_text.insert(tk.END, "Análisis de tendencias no implementado aún\n")

    def run_snr_analysis(self, raw=True):
        """Ejecutar análisis comprehensivo de SNR (Signal-to-Noise Ratio)"""
        mode = "Raw" if raw else "Filtrado"

        # Determinar qué columnas usar
        if raw:
            required_cols = ['Sample', 'KEITHLEY Voltage (V)', 'TIVA Voltage (V)']
            signal_col = 'TIVA Voltage (V)'
            title_suffix = 'TIVA Raw vs Keithley'

        # Verificar columnas requeridas
        missing_cols = [col for col in required_cols if col not in self.csv_data.columns]

        if missing_cols:
            self.analysis_info_text.insert(tk.END, f'Columnas requeridas faltantes para análisis SNR ({mode}): {", ".join(missing_cols)}\n')
            return

        if len(self.csv_data) < 50:
            self.analysis_info_text.insert(tk.END, f'Datos insuficientes para análisis SNR ({mode}) - mínimo 50 puntos requeridos\n')
            self.analysis_info_text.insert(tk.END, f'Puntos disponibles: {len(self.csv_data)}\n')
            return

        # Preparar datos
        samples = self.csv_data['Sample'].values
        keithley_voltage = self.csv_data['KEITHLEY Voltage (V)'].values
        signal_voltage = self.csv_data[signal_col].values

        # Obtener parámetros de la UI
        window_size = self.analysis_window_size.get()
        step_size = self.analysis_step_size.get()

        # Crear figura comprehensiva con layout 4x4
        fig = plt.figure(figsize=(16, 12), dpi=100)
        fig.suptitle(f'Análisis Comprehensivo SNR - {title_suffix}', fontsize=16, fontweight='bold')

        # Panel 1: Evolución temporal del SNR
        ax1 = plt.subplot(4, 4, 1)
        self._plot_snr_temporal(ax1, keithley_voltage, signal_voltage, samples, mode)

        # Panel 2: Componentes de señal (señal vs ruido)
        ax2 = plt.subplot(4, 4, 2)
        self._plot_signal_components(ax2, keithley_voltage, signal_voltage, samples)

        # Panel 3: Histogramas de SNR
        ax3 = plt.subplot(4, 4, 3)
        self._plot_snr_histogram(ax3, keithley_voltage, signal_voltage, samples)

        # Panel 4: Análisis de estabilidad SNR
        ax4 = plt.subplot(4, 4, 4)
        self._plot_snr_stability(ax4, keithley_voltage, signal_voltage, samples)

        # Panel 5: Comparación de métodos SNR
        ax5 = plt.subplot(4, 4, 5)
        self._plot_snr_methods_comparison(ax5, keithley_voltage, signal_voltage, samples)

        # Panel 6: Análisis de ruido
        ax6 = plt.subplot(4, 4, 6)
        self._plot_noise_analysis(ax6, keithley_voltage, signal_voltage, samples)

        # Panel 7: SNR vs amplitud de señal
        ax7 = plt.subplot(4, 4, 7)
        self._plot_snr_vs_amplitude(ax7, keithley_voltage, signal_voltage, samples)

        # Panel 8: Detección de outliers en SNR
        ax8 = plt.subplot(4, 4, 8)
        self._plot_snr_outliers(ax8, keithley_voltage, signal_voltage, samples)

        # Panel 9: Autocorrelación del ruido
        ax9 = plt.subplot(4, 4, 9)
        self._plot_noise_autocorr(ax9, keithley_voltage, signal_voltage)

        # Panel 10: Espectro del ruido
        ax10 = plt.subplot(4, 4, 10)
        self._plot_noise_spectrum(ax10, keithley_voltage, signal_voltage, samples)

        # Panel 11: Métricas de calidad de señal
        ax11 = plt.subplot(4, 4, 11)
        self._plot_signal_quality_metrics(ax11, keithley_voltage, signal_voltage, samples)

        # Panel 12: Análisis de tendencias SNR
        ax12 = plt.subplot(4, 4, 12)
        self._plot_snr_trends(ax12, keithley_voltage, signal_voltage, samples)

        # Panel 14: Resumen estadístico SNR
        ax14 = plt.subplot(4, 4, 14)
        self._plot_snr_summary_stats(ax14, keithley_voltage, signal_voltage, samples)

        # Panel 15: Análisis de variabilidad
        ax15 = plt.subplot(4, 4, 15)
        self._plot_snr_variability(ax15, keithley_voltage, signal_voltage, samples)

        # Panel 16: Matriz de correlación de métricas
        ax16 = plt.subplot(4, 4, 16)
        self._plot_snr_correlation_matrix(ax16, keithley_voltage, signal_voltage, samples)

        plt.tight_layout(h_pad=0.3, w_pad=0.3)

        # Determinar el tipo de análisis para el sistema de pestañas
        analysis_type = 'snr' if raw else 'snr_filtered'

        # Mostrar en la pestaña correspondiente
        self.display_analysis_figure(fig, analysis_type)

        # Calcular métricas globales para el resumen
        times, snr_values = self.calculate_snr_sliding(keithley_voltage, signal_voltage, samples,
                                                      window_size=window_size, step=step_size)

        if snr_values:
            snr_mean = np.mean(snr_values)
            snr_std = np.std(snr_values)
            snr_min = np.min(snr_values)
            snr_max = np.max(snr_values)

            # Almacenar resultados
            results = {
                'mode': mode,
                'signal_type': 'raw' if raw else 'filtered',
                'window_size': window_size,
                'step_size': step_size,
                'total_samples': len(samples),
                'snr_samples': len(snr_values),
                'snr_mean': float(snr_mean),
                'snr_std': float(snr_std),
                'snr_min': float(snr_min),
                'snr_max': float(snr_max),
                'snr_range': float(snr_max - snr_min),
                'global_summary': {
                    'SNR Promedio (dB)': f'{snr_mean:.2f}',
                    'Desviación Estándar SNR (dB)': f'{snr_std:.2f}',
                    'SNR Mínimo (dB)': f'{snr_min:.2f}',
                    'SNR Máximo (dB)': f'{snr_max:.2f}',
                    'Rango SNR (dB)': f'{snr_max - snr_min:.2f}',
                    'Ventana de Análisis': f'{window_size} puntos',
                    'Paso de Análisis': f'{step_size} puntos'
                }
            }

            self.analysis_results[analysis_type] = results

            # Actualizar información del análisis
            self.analysis_info_text.delete(1.0, tk.END)
            self.analysis_info_text.insert(tk.END, f"Análisis SNR ({mode}) completado exitosamente\n\n")
            self.analysis_info_text.insert(tk.END, f"Parámetros utilizados:\n")
            self.analysis_info_text.insert(tk.END, f"• Tamaño de ventana: {window_size} puntos\n")
            self.analysis_info_text.insert(tk.END, f"• Paso: {step_size} puntos\n")
            self.analysis_info_text.insert(tk.END, f"• Total de muestras: {len(samples)}\n")
            self.analysis_info_text.insert(tk.END, f"• Muestras SNR calculadas: {len(snr_values)}\n\n")
            self.analysis_info_text.insert(tk.END, f"Métricas SNR:\n")
            self.analysis_info_text.insert(tk.END, f"• Promedio: {snr_mean:.2f} dB\n")
            self.analysis_info_text.insert(tk.END, f"• Desviación estándar: {snr_std:.2f} dB\n")
            self.analysis_info_text.insert(tk.END, f"• Rango: {snr_max - snr_min:.2f} dB\n")
            self.analysis_info_text.insert(tk.END, f"• Mínimo: {snr_min:.2f} dB\n")
            self.analysis_info_text.insert(tk.END, f"• Máximo: {snr_max:.2f} dB\n")
        else:
            self.analysis_info_text.insert(tk.END, f"No se pudieron calcular valores SNR para el análisis ({mode})\n")

    def run_cycle_average_analysis(self):
        """Placeholder for cycle average analysis"""
        self.analysis_info_text.insert(tk.END, "Análisis de ciclos promedio no implementado aún\n")

    def run_whitestone_bridge_analysis(self):
        """Placeholder for Wheatstone bridge analysis"""
        self.analysis_info_text.insert(tk.END, "Análisis puente Wheatstone no implementado aún\n")

    def run_presion_analysis(self):
        """Placeholder for pressure analysis"""
        self.analysis_info_text.insert(tk.END, "Análisis de presión no implementado aún\n")

    def run_estadisticas_analysis(self):
        """Placeholder for statistics analysis"""
        self.analysis_info_text.insert(tk.END, "Análisis estadístico no implementado aún\n")

    # Métodos de control de adquisición
    def start_acquisition(self):
        """Iniciar la adquisición de datos"""
        if acquisition_instruments.acquisition_running:
            messagebox.showwarning("Advertencia", "La adquisición ya está en ejecución")
            return

        try:
            # Actualizar configuración global
            self.update_global_config()

            # Recolectar parámetros de setpoint
            params = {
                'setpoint_inicial': self.setpoint_inicial.get(),
                'setpoint_final': self.setpoint_final.get(),
                'setpoint_intervalo': self.setpoint_intervalo.get(),
                'num_puntos_intermedios': self.num_puntos_intermedios.get(),
                'num_ciclos': self.num_ciclos.get(),
                'intermediate_mode': self.intermediate_mode.get(),
                'custom_points_text': self.custom_points_text.get(),
                'stability_time': self.stability_time.get(),
                'enable_stability': self.enable_stability.get(),
                'file_label': self.file_label.get()
            }

            # Iniciar adquisición usando la función del módulo
            acquisition_instruments.iniciar_adquisicion(params)

            # Actualizar estado local
            self.acquisition_running = True

            # Actualizar botones
            self.btn_start.config(state=tk.DISABLED)
            self.btn_pause.config(state=tk.NORMAL)
            self.btn_stop.config(state=tk.NORMAL)

            self.status_text.set("Adquisición iniciada")
            self.log_message("Adquisición iniciada")

            # Iniciar monitoreo del estado de adquisición
            self.start_acquisition_monitoring()

        except Exception as e:
            messagebox.showerror("Error", f"Error al iniciar adquisición: {e}")
            self.logger.error(f"Error starting acquisition: {e}")

    def pause_resume_acquisition(self):
        """Pausar o reanudar la adquisición"""
        try:
            acquisition_instruments.pausar_reanudar_adquisicion()

            # Actualizar estado del botón y texto de estado
            if acquisition_instruments.acquisition_paused:
                self.btn_pause.config(text="▶️ Reanudar")
                self.status_text.set("Adquisición pausada")
                self.log_message("Adquisición pausada")
            else:
                self.btn_pause.config(text="⏸️ Pausar/Reanudar")
                self.status_text.set("Adquisición reanudada")
                self.log_message("Adquisición reanudada")

        except Exception as e:
            messagebox.showerror("Error", f"Error al pausar/reanudar adquisición: {e}")
            self.logger.error(f"Error pausing/resuming acquisition: {e}")

    def stop_acquisition(self):
        """Detener la adquisición"""
        try:
            acquisition_instruments.detener_adquisicion()

            # Actualizar estado local
            self.acquisition_running = False

            # Actualizar botones
            self.btn_start.config(state=tk.NORMAL)
            self.btn_pause.config(state=tk.DISABLED)
            self.btn_stop.config(state=tk.DISABLED)
            self.btn_pause.config(text="⏸️ Pausar/Reanudar")

            self.status_text.set("Adquisición detenida")
            self.log_message("Adquisición detenida")

        except Exception as e:
            messagebox.showerror("Error", f"Error al detener adquisición: {e}")
            self.logger.error(f"Error stopping acquisition: {e}")

    def start_acquisition_monitoring(self):
        """Iniciar monitoreo del estado de adquisición"""
        self.monitoring_active = True

        def monitor():
            while self.monitoring_active:
                try:
                    # Verificar si la adquisición sigue corriendo
                    if not acquisition_instruments.acquisition_running and self.acquisition_running:
                        # La adquisición terminó desde el módulo
                        self.acquisition_running = False
                        self.btn_start.config(state=tk.NORMAL)
                        self.btn_pause.config(state=tk.DISABLED)
                        self.btn_stop.config(state=tk.DISABLED)
                        self.btn_pause.config(text="⏸️ Pausar/Reanudar")
                        self.status_text.set("Adquisición completada")
                        self.log_message("Adquisición completada automáticamente")
                        break

                    # Verificar estado de pausa
                    if acquisition_instruments.acquisition_paused != (self.btn_pause.cget("text") == "▶️ Reanudar"):
                        if acquisition_instruments.acquisition_paused:
                            self.btn_pause.config(text="▶️ Reanudar")
                            self.status_text.set("Adquisición pausada")
                        else:
                            self.btn_pause.config(text="⏸️ Pausar/Reanudar")
                            self.status_text.set("Adquisición en ejecución")

                except Exception as e:
                    self.logger.warning(f"Error en monitoreo de adquisición: {e}")

                time.sleep(0.5)  # Verificar cada medio segundo

        # Iniciar monitoreo en un hilo separado
        monitoring_thread = threading.Thread(target=monitor, daemon=True)
        monitoring_thread.start()

    def log_message(self, message):
        """Registrar mensaje en el log"""
        self.logger.info(message)

    def update_global_config(self):
        """Actualizar configuración global cuando cambian parámetros"""
        # Aquí se pueden agregar actualizaciones de configuración global si es necesario
        pass


def main():
    """Función principal"""
    root = tk.Tk()
    app = AcquisitionGUI(root)
    root.mainloop()


if __name__ == '__main__':
    main()