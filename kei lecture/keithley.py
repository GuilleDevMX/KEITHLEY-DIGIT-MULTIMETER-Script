import serial
import csv
import numpy as np
import time
import threading
import os
import signal
import sys
import logging
from datetime import datetime
from pathlib import Path

# Importar la clase KeithleyAcquisition
from acquisition import KeithleyAcquisition

# === CONFIGURACIÓN TIVA ===
SERIAL_PORT = 'COM6'      # Cambia si usas otro puerto
BAUDRATE = 230400
TIMEOUT = 1.0
CSV_BUFFER_SIZE = 20      # Guarda cada 20 muestras

# Configuración por defecto del Keithley
DEFAULT_KEITHLEY_CONFIG = {
    'output_dir': 'lecturas',
    'experiment_label': 'adquisicion_presion',
    'nplc_cycles': 1,               # Ciclos NPLC (precisión: 0.001 = alta precisión)
    'samples_per_count': 1,         # Muestras por bloque
    'num_blocks': 50,               # Número de bloques (si no infinito)
    'infinite_mode': False,         # False = modo finito, True = infinito
    'quiet': False                  # False = mostrar prompts de confirmación
}

# === CONFIGURACIÓN Global ===
ser_tiva = None
acquisition_running = False
acquisition_paused = False
logger = None
keithley_acquirer_global = None
thread_acquisition = None

def setup_logging(level=logging.INFO, log_file=None):
    """
    Configura el sistema de logging

    Args:
        level: Nivel de logging (DEBUG, INFO, WARNING, ERROR)
        log_file: Archivo opcional para guardar logs
    """
    global logger

    # Configurar formato
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    # Handler para consola
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    console_handler.setLevel(level)

    # Handler para archivo (opcional)
    file_handler = None
    if log_file:
        file_handler = logging.FileHandler(log_file)
        file_handler.setFormatter(formatter)
        file_handler.setLevel(level)

    # Configurar logger
    logger = logging.getLogger('AdquisicionPresion')
    logger.setLevel(level)
    logger.addHandler(console_handler)
    if file_handler:
        logger.addHandler(file_handler)

    return logger


def test_instrument_connections():
    """
    Prueba las conexiones con los instrumentos

    Returns:
        bool: True si las conexiones son exitosas
    """
    logger.info("Probando conexiones con instrumentos...")

    try:
        # Probar conexión con Keithley
        logger.info("Probando conexión con Keithley...")
        test_keithley = KeithleyAcquisition(DEFAULT_KEITHLEY_CONFIG, logger)
        with test_keithley.instrument_connection():
            logger.info("✅ Conexión con Keithley exitosa")
        test_keithley = None

        # Probar conexión con tiva
        logger.info("Probando conexión con tiva...")
        import serial
        test_tiva = serial.Serial(port="COM6", baudrate=230400, timeout=1)
        time.sleep(0.5)
        if test_tiva.is_open:
            logger.info("✅ Conexión con tiva exitosa")
            test_tiva.close()
        else:
            logger.warning("⚠️ No se pudo verificar conexión con tiva")
        return True

    except Exception as e:
        logger.error(f"❌ Error en conexiones: {e}")
        return False


def create_output_directory(output_dir):
    """
    Crea el directorio de salida si no existe

    Args:
        output_dir: Ruta del directorio
    """
    try:
        Path(output_dir).mkdir(parents=True, exist_ok=True)
        logger.info(f"Directorio de salida creado/verificado: {output_dir}")
    except Exception as e:
        logger.error(f"Error creando directorio de salida {output_dir}: {e}")
        raise


# =============================================================================
# FUNCIONES DE EJECUCIÓN
# =============================================================================

def run_acquisition_experiment(keithley_config=None, acquisition_params=None, test_connections=True):
    """
    Ejecuta un experimento completo de adquisición

    Args:
        keithley_config: Configuración del Keithley (opcional, usa defaults)
        acquisition_params: Parámetros de adquisición (opcional, usa defaults)
        test_connections: Si probar conexiones antes de iniciar
    """
    global acquisition_running, acquisition_paused, logger

    # Usar configuraciones por defecto si no se proporcionan
    keithley_config = keithley_config or DEFAULT_KEITHLEY_CONFIG.copy()
    acquisition_params = acquisition_params or DEFAULT_ACQUISITION_PARAMS.copy()

    # Configurar logging si no está configurado
    if logger is None:
        setup_logging()

    logger.info("=" * 60)
    logger.info("INICIANDO EXPERIMENTO DE ADQUISICIÓN PRESIÓN-VOLTAJE")
    logger.info("=" * 60)

    # Mostrar configuración
    logger.info("Configuración del experimento:")
    logger.info(f"  Keithley - Directorio: {keithley_config['output_dir']}")
    logger.info(f"  Keithley - Etiqueta: {keithley_config['experiment_label']}")
    logger.info(f"  Keithley - NPLC: {keithley_config['nplc_cycles']}")

    # Validar configuración
    if not validate_configuration(keithley_config, acquisition_params):
        logger.error("Configuración inválida. Abortando experimento.")
        return False

    # Crear directorio de salida
    create_output_directory(keithley_config['output_dir'])

    # Probar conexiones si se solicita
    if test_connections:
        if not test_instrument_connections():
            logger.error("Fallaron las pruebas de conexión. Abortando experimento.")
            return False

    # Configurar manejo de señales para interrupción graceful
    def signal_handler(signum, frame):
        global acquisition_running
        logger.info("Señal de interrupción recibida. Deteniendo adquisición...")
        acquisition_running = False

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # Inicializar variables globales
    acquisition_running = False
    acquisition_paused = False

    global thread_acquisition
    thread_acquisition = None

    try:
        # Iniciar adquisición
        logger.info("🚀 Iniciando adquisición...")
        acquisition_running = True

        thread_acquisition = threading.Thread(
            target=acquisition_loop,
            args=(acquisition_params, keithley_config),
            name="AcquisitionThread"
        )
        thread_acquisition.start()

        logger.info("✅ Adquisición iniciada en thread separado")
        logger.info("Presiona Ctrl+C para detener la adquisición")

        # Mantener el programa corriendo mientras la adquisición está activa
        while acquisition_running:
            time.sleep(1)

        # Esperar a que termine el thread
        if thread_acquisition and thread_acquisition.is_alive():
            logger.info("Esperando que termine el thread de adquisición...")
            thread_acquisition.join(timeout=10.0)

        # Limpiar recursos
        detener_adquisicion()

        logger.info("✅ Experimento completado exitosamente")
        return True

    except KeyboardInterrupt:
        logger.info("Interrupción por teclado detectada")
        detener_adquisicion()
        return False

    except Exception as e:
        logger.error(f"Error durante el experimento: {e}")
        detener_adquisicion()
        return False

    finally:
        # Limpieza final
        if thread_acquisition and thread_acquisition.is_alive():
            thread_acquisition.join(timeout=5.0)

        logger.info("=" * 60)
        logger.info("EXPERIMENTO FINALIZADO")
        logger.info("=" * 60)

# === CRC-16-CCITT (igual que en Tiva C) ===
def calcular_crc16_ccitt(data: bytes) -> int:
    crc = 0xFFFF
    for byte in data:
        crc ^= (byte << 8)
        for _ in range(8):
            if crc & 0x8000:
                crc = (crc << 1) ^ 0x1021
            else:
                crc <<= 1
            crc &= 0xFFFF
    return crc

# === Validar y decodificar paquete de 12 bytes ===
def recibir_paquete(data_12bytes: bytes):
    if len(data_12bytes) != 12 or data_12bytes[10:] != b'\r\n':
        return None, None

    payload = data_12bytes[:8]
    crc_recibido = int.from_bytes(data_12bytes[8:10], 'little')
    crc_calculado = calcular_crc16_ccitt(payload)

    if crc_recibido != crc_calculado:
        print(f"CRC error: recibido 0x{crc_recibido:04X}, calculado 0x{crc_calculado:04X}")
        return None, None

    voltage, temperature = struct.unpack('<ff', payload)
    return voltage, temperature

# === Manejador de Ctrl+C ===
def signal_handler(sig, frame):
    print("\nInterrupción detectada. Terminando...")
    stop_acquisition()
    sys.exit(0)

def setup_signal_handler():
    signal.signal(signal.SIGINT, signal_handler)

# === Configurar puerto serial ===
def setup_serial():
    global ser_tiva
    try:
        ser_tiva = serial.Serial(
            port=SERIAL_PORT,
            baudrate=BAUDRATE,
            bytesize=serial.EIGHTBITS,
            parity=serial.PARITY_NONE,
            stopbits=serial.STOPBITS_ONE,
            timeout=TIMEOUT
        )
        time.sleep(2)
        print(f"Conexión serial establecida en {SERIAL_PORT} @ {BAUDRATE} baudios")
        return True
    except serial.SerialException as e:
        print(f"Error: No se pudo abrir {SERIAL_PORT}: {e}")
        print("   Verifica que el Tiva esté conectado y el puerto sea correcto.")
        return False

# === Iniciar adquisición ===
def start_acquisition():
    global acquisition_running
    if acquisition_running:
        print("Adquisición ya en curso.")
        return
    acquisition_running = True
    threading.Thread(target=acquire_data, daemon=True).start()

# === Detener adquisición ===
def stop_acquisition():
    global acquisition_running
    acquisition_running = False
    if ser_tiva and ser_tiva.is_open:
        try:
            ser_tiva.close()
            print("Puerto serial cerrado.")
        except:
            pass

def conversion_counts_to_voltage(counts):
    # Suponiendo que los counts son de un ADC de 24 bits con referencia de 2.5V, PGA = 32
    V_ref = 5
    pga = 32
    max_counts = 2**24 - 1
    voltage = (counts / max_counts) * V_ref / pga
    return voltage

# === Función principal de adquisición ===
def acquire_data():
    global acquisition_running, ser_tiva

    if not setup_serial():
        acquisition_running = False
        return

    # --- Nombre de archivos con timestamp ---
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    csv_filename = f'tiva_data_{timestamp}.csv'

    # --- Archivos ---
    with open(csv_filename, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(['Muestra', 'Tiempo (s)', 'Voltaje (V)', 'Temperatura (°C)'])

    # --- Variables de adquisición ---
    start_time = time.time()
    sample_count = 0
    buffer = []
    voltages = []
    temperatures = []
    acquisition_running = True

    print("Adquisición iniciada. Presiona Ctrl+C para detener antes.")

    try:
        while acquisition_running and (time.time() - start_time) < 60.0:
            try:
                # Leer paquete completo (12 bytes)
                raw_line = ser_tiva.readline()
                if len(raw_line) != 12:
                    print(f"Paquete inválido: longitud {len(raw_line)}, esperado 12")
                    time.sleep(0.001)
                    continue

                current_time = time.time() - start_time
                voltage, temperature = recibir_paquete(raw_line)

                if voltage is not None and temperature is not None:
                    # --- Guardar en buffer ---
                    buffer.append([
                        sample_count,
                        f"{current_time:.6f}",
                        f"{voltage:.6f}",
                        f"{temperature:.3f}"
                    ])
                    voltages.append(voltage)
                    temperatures.append(temperature)

                    sample_count += 1
                else:
                    # Paquete corrupto: registrar como error (opcional)
                    pass

                # --- Guardar en CSV cada N muestras ---
                if len(buffer) >= CSV_BUFFER_SIZE:
                    with open(csv_filename, 'a', newline='', encoding='utf-8') as f:
                        writer = csv.writer(f)
                        writer.writerows(buffer)
                    buffer.clear()

                time.sleep(0.001)  # ~1kHz max

            except serial.SerialException:
                print("Error de comunicación serial.")
                break
            except Exception as e:
                print(f"Error inesperado: {e}")
                break

        # --- Guardar datos restantes ---
        if buffer:
            with open(csv_filename, 'a', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerows(buffer)

        # --- Estadísticas finales ---
        total_time = time.time() - start_time
        sampling_rate = sample_count / total_time if total_time > 0 else 0

        if voltages:
            avg_voltage = np.mean(voltages)
            std_voltage = np.std(voltages)
            avg_temp = np.mean(temperatures)
            std_temp = np.std(temperatures)
        else:
            avg_voltage = std_voltage = avg_temp = std_temp = 0.0

        # --- Escribir resumen en CSV ---
        with open(csv_filename, 'a', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow([])
            writer.writerow(['--- RESUMEN ---'])
            writer.writerow(['Muestras totales', sample_count])
            writer.writerow(['Tiempo total (s)', f"{total_time:.3f}"])
            writer.writerow(['Frecuencia (Hz)', f"{sampling_rate:.2f}"])
            writer.writerow(['Voltaje promedio (V)', f"{avg_voltage:.6f}"])
            writer.writerow(['Voltaje desv. std', f"{std_voltage:.6f}"])
            writer.writerow(['Temperatura promedio (°C)', f"{avg_temp:.3f}"])
            writer.writerow(['Temperatura desv. std', f"{std_temp:.3f}"])

        print("\n" + "="*50)
        print("ADQUISICIÓN COMPLETADA")
        print(f"   Archivo CSV: {csv_filename}")
        print(f"   Muestras: {sample_count}")
        print(f"   Tiempo: {total_time:.2f} s")
        print(f"   Frecuencia: {sampling_rate:.2f} Hz")
        print(f"   Voltaje promedio: {avg_voltage:.6f} V")
        print(f"   Temperatura promedio: {avg_temp:.3f} °C")
        print("="*50)

    except Exception as e:
        print(f"Error crítico: {e}")
    finally:
        acquisition_running = False
        if ser_tiva and ser_tiva.is_open:
            ser_tiva.close()
            print("Puerto serial cerrado.")

# === MAIN ===
if __name__ == "__main__":
    setup_signal_handler()
    print("Iniciando adquisición de datos desde Tiva C (Voltaje + Temperatura) - 10 segundos")
    print(f"Puerto: {SERIAL_PORT} | Baudios: {BAUDRATE}")
    print("Presiona Ctrl+C para detener.\n")

    try:
        acquire_data()
    except KeyboardInterrupt:
        print("\nDetención solicitada por el usuario.")
    except Exception as e:
        print(f"Error fatal: {e}")
        sys.exit(1)