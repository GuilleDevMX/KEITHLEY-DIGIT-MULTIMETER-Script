import pyvisa
import time
import csv
import matplotlib.pyplot as plt
from datetime import datetime
import logging
import threading
import sys
import argparse

# Configurar el parser de argumentos
parser = argparse.ArgumentParser(
    description='Sistema de adquisición de datos Keithley con análisis estadístico',
    formatter_class=argparse.RawDescriptionHelpFormatter,
    epilog='''
Ejemplos de uso:
  # Adquisición básica con gráficas completas
  python main.py --label "experimento1" --samples 1000 --nplc 1 --blocks 10

  # Adquisición con gráficas básicas únicamente
  python main.py --label "experimento2" --samples 500 --nplc 0.1 --blocks 5 --no-stats

  # Adquisición con NPLC personalizado (requiere --force)
  python main.py --label "experimento3" --samples 2000 --nplc 5 --force --blocks 0
    '''
)

parser.add_argument('--label', '-l', type=str, default='experimento',
                    help='Etiqueta del experimento (default: experimento)')
parser.add_argument('--samples', '-s', type=int, default=2000,
                    help='Muestras por conteo (100-2000, default: 2000)')
parser.add_argument('--nplc', '-n', type=str, default='10',
                    help='Ciclos NPLC (0.001-100 o MINimum/MAXimum, default: 10)')
parser.add_argument('--blocks', '-b', type=int, default=50,
                    help='Número de bloques (0=indefinido, 1-1000, default: 50)')
parser.add_argument('--force', '-f', action='store_true',
                    help='Forzar valores NPLC personalizados')
parser.add_argument('--no-stats', '-ns', action='store_true',
                    help='Solo generar gráficas básicas (sin estadísticas avanzadas)')

# Parsear argumentos
args = parser.parse_args()

# Extraer valores de los argumentos
experiment_label = args.label
samples_per_count = args.samples
nplc_cycles_input = args.nplc
num_blocks = args.blocks
force_nplc = args.force
no_stats = args.no_stats

# Valores válidos para NPLCycles
VALID_NPLC_VALUES = [0.001, 0.006, 0.02, 0.06, 0.2, 0.6, 1, 2, 10, 100, "MINimum", "MAXimum"]

# Validar y procesar muestras por conteo
if samples_per_count < 100 or samples_per_count > 2000:
    print(f"⚠️ Muestras por conteo debe estar entre 100-2000. Usando 2000.")
    samples_per_count = 2000

# Validar y procesar NPLCycles
try:
    # Si es MINimum o MAXimum, mantener como string
    if nplc_cycles_input in ["MINimum", "MAXimum"]:
        if not force_nplc and nplc_cycles_input not in VALID_NPLC_VALUES:
            print(f"⚠️ NPLCycles debe ser uno de {VALID_NPLC_VALUES}. Usando 10.")
            print(f"💡 Use --force para permitir valores personalizados.")
            nplc_cycles = 10
        else:
            nplc_cycles = nplc_cycles_input
    else:
        # Intentar convertir a float
        nplc_cycles = float(nplc_cycles_input)
        if not force_nplc and nplc_cycles not in VALID_NPLC_VALUES:
            print(f"⚠️ NPLCycles debe ser uno de {VALID_NPLC_VALUES}. Usando 10.")
            print(f"💡 Use --force para permitir valores personalizados.")
            nplc_cycles = 10
except ValueError:
    print(f"⚠️ Valor inválido para NPLCycles. Usando 10.")
    nplc_cycles = 10

# Validar número de bloques
if num_blocks < 0 or num_blocks > 1000:
    print(f"⚠️ Número de bloques debe estar entre 0-1000 (0=indefinido). Usando 50.")
    num_blocks = 50

# Determinar si es modo indefinido
infinite_mode = (num_blocks == 0)

print(f"🏷️ Etiqueta del experimento: '{experiment_label}'")
print(f"📊 Muestras por conteo: {samples_per_count}")
print(f"⚡ NPLCycles: {nplc_cycles}")
if force_nplc:
    print(f"🔓 Modo fuerza activado para NPLCycles")
if no_stats:
    print(f"📈 Gráficas de estadísticas: deshabilitadas (solo datos básicos)")
else:
    print(f"📈 Gráficas de estadísticas: habilitadas")
print(f"🔢 Número de bloques: {'indefinido' if infinite_mode else num_blocks}")

# Agregar numpy para cálculos estadísticos avanzados
try:
    import numpy as np
    NUMPY_AVAILABLE = True
except ImportError:
    print("⚠️ NumPy no disponible. Algunas estadísticas avanzadas estarán limitadas.")
    NUMPY_AVAILABLE = False
    np = None

# Agregar scipy para análisis estadístico avanzado
try:
    from scipy import stats as scipy_stats
    SCIPY_AVAILABLE = True
except ImportError:
    print("⚠️ SciPy no disponible. El análisis KDE estará limitado.")
    SCIPY_AVAILABLE = False
    scipy_stats = None

# Intentar importar keyboard para interrupción
try:
    import keyboard
    KEYBOARD_AVAILABLE = True
except ImportError:
    print("⚠️ Módulo 'keyboard' no disponible. Instala con: pip install keyboard")
    print("   La interrupción desde teclado no estará disponible.")
    KEYBOARD_AVAILABLE = False
    keyboard = None

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(f'keithley_acquisition_{datetime.now().strftime("%Y%m%d")}.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)
logger.info(f"Experiment label set to: {experiment_label}")
logger.info(f"Samples per count set to: {samples_per_count}")
logger.info(f"NPLCycles set to: {nplc_cycles}")
if force_nplc:
    logger.info("Force mode enabled for NPLCycles")
if no_stats:
    logger.info("Statistics plots disabled - basic plots only")
else:
    logger.info("Statistics plots enabled")
logger.info(f"Number of blocks set to: {'infinite' if infinite_mode else num_blocks}")

readings = []
total_samples_expected = 0
stop_acquisition = False  # Variable global para controlar interrupción

def check_for_interruption():
    """Función que se ejecuta en un thread separado para detectar interrupción"""
    global stop_acquisition

    if not KEYBOARD_AVAILABLE:
        print("\n⚠️ Interrupción por teclado no disponible (instala 'keyboard' con pip)")
        logger.warning("Keyboard interruption not available - install 'keyboard' module")
        return

    print("\n🔴 Presiona 'q' o 'ESC' para detener la adquisición...")
    logger.info("Interruption listener started - press 'q' or 'ESC' to stop")

    while not stop_acquisition:
        try:
            if keyboard.is_pressed('q') or keyboard.is_pressed('esc'):
                stop_acquisition = True
                print("\n🛑 Interrupción detectada! Deteniendo adquisición...")
                logger.warning("Acquisition interrupted by user")
                break
            time.sleep(0.1)  # Pequeña pausa para no consumir CPU
        except Exception as e:
            logger.error(f"Error in interruption check: {e}")
            break

def calculate_advanced_statistics(voltages):
    """Calcula estadísticas avanzadas de los datos de voltaje"""
    if not voltages:
        return {}

    stats = {}

    if NUMPY_AVAILABLE:
        voltages_array = np.array(voltages)

        # Estadísticas básicas con numpy
        stats['mean'] = np.mean(voltages_array)
        stats['std'] = np.std(voltages_array, ddof=1)  # ddof=1 para muestra
        stats['variance'] = np.var(voltages_array, ddof=1)
        stats['min'] = np.min(voltages_array)
        stats['max'] = np.max(voltages_array)
        stats['range'] = stats['max'] - stats['min']

        # Desviación media absoluta (MAD)
        stats['mad'] = np.mean(np.abs(voltages_array - stats['mean']))

        # Coeficiente de variación
        stats['cv'] = (stats['std'] / stats['mean']) * 100 if stats['mean'] != 0 else 0

        # Asimetría (skewness)
        if SCIPY_AVAILABLE:
            stats['skewness'] = scipy_stats.skew(voltages_array)
        else:
            stats['skewness'] = np.mean(((voltages_array - stats['mean']) / stats['std']) ** 3) if stats['std'] != 0 else 0

        # Curtosis
        if SCIPY_AVAILABLE:
            stats['kurtosis'] = scipy_stats.kurtosis(voltages_array)
        else:
            stats['kurtosis'] = np.mean(((voltages_array - stats['mean']) / stats['std']) ** 4) - 3 if stats['std'] != 0 else 0

        # Autocorrelación (primer lag)
        if len(voltages_array) > 1:
            stats['autocorr_lag1'] = np.corrcoef(voltages_array[:-1], voltages_array[1:])[0, 1]

        # Correlación con el índice de tiempo (tendencia)
        time_indices = np.arange(len(voltages_array))
        if len(time_indices) > 1:
            stats['time_correlation'] = np.corrcoef(time_indices, voltages_array)[0, 1]

    else:
        # Cálculos básicos sin numpy
        n = len(voltages)
        mean = sum(voltages) / n

        # Varianza
        variance = sum((x - mean) ** 2 for x in voltages) / (n - 1) if n > 1 else 0
        std = variance ** 0.5

        # MAD
        mad = sum(abs(x - mean) for x in voltages) / n

        stats.update({
            'mean': mean,
            'std': std,
            'variance': variance,
            'mad': mad,
            'min': min(voltages),
            'max': max(voltages),
            'range': max(voltages) - min(voltages)
        })

    return stats

# Create a resource manager, preferring NI-VISA backend if available
try:
    rm = pyvisa.ResourceManager('@ni')
    print("Using NI-VISA backend.")
    logger.info("Using NI-VISA backend")
except Exception as e:
    logger.warning(f"NI-VISA not available, using default backend: {e}")
    rm = pyvisa.ResourceManager()
    print("Using default backend (likely pyvisa-py). Recommend installing NI-VISA for better USBTMC support.")

# List available resources for verification
print("Available resources:", rm.list_resources())
logger.info(f"Available resources: {list(rm.list_resources())}")

# Use the correct resource name from your output
resource_name = 'USB0::0x05E6::0x2110::1422671::INSTR'
logger.info(f"Using resource: {resource_name}")

try:
    # Open the connection to the instrument
    inst = rm.open_resource(resource_name)
    logger.info("Instrument connection opened")

    # Set a reasonable timeout based on samples and NPLCycles
    # Estimación: tiempo base + (muestras * NPLCycles * factor_conversion)
    base_timeout = 30000  # 30 segundos base
    nplc_factor = float(nplc_cycles) if isinstance(nplc_cycles, (int, float)) else 10
    estimated_block_time = samples_per_count * nplc_factor * 0.0001  # Factor de conversión aproximado
    dynamic_timeout = max(30000, int(base_timeout + estimated_block_time * 1000))  # Mínimo 30 segundos
    inst.timeout = dynamic_timeout
    logger.info(f"Timeout set to {inst.timeout}ms (based on {samples_per_count} samples, NPLCycles={nplc_cycles})")

    # Switch to remote mode
    inst.write(':SYSTem:REMote')
    time.sleep(0.5)  # Short delay for mode switch
    logger.debug("Switched to remote mode")

    # Reset the instrument to default settings
    inst.write('*RST')
    time.sleep(1)  # Wait for reset
    logger.debug("Instrument reset completed")

    # Clear status
    inst.write('*CLS')
    logger.debug("Status cleared")

    # # Verify no errors after reset
    # if not check_instrument_errors(inst):
    #     raise Exception("Errors detected after instrument reset")

    # Configure for DC voltage measurement
    inst.write('CONFigure:VOLTage:DC')
    logger.debug("Configured for DC voltage measurement")

    # Enable auto-ranging
    inst.write('VOLTage:DC:RANGe:AUTO ON')
    logger.debug("Auto-ranging enabled")

    # Set integration time for measurement
    inst.write(f'SENSe:VOLTage:DC:NPLCycles {nplc_cycles}')
    logger.debug(f"NPLCycles set to {nplc_cycles}")

    # Verify NPLCycles was set correctly
    try:
        current_nplc = inst.query('SENSe:VOLTage:DC:NPLCycles?').strip()
        logger.debug(f"NPLCycles verification: set={nplc_cycles}, read={current_nplc}")
        if str(nplc_cycles) != current_nplc:
            logger.warning(f"NPLCycles verification failed: expected {nplc_cycles}, got {current_nplc}")
    except Exception as e:
        logger.warning(f"Could not verify NPLCycles setting: {e}")

    # Create CSV file with timestamp and experiment label
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    csv_filename = f'dc_voltage_readings_{experiment_label}_{timestamp}.csv'
    logger.info(f"CSV file will be: {csv_filename}")

    # Initialize CSV file with header
    with open(csv_filename, 'w', newline='') as csvfile:
        writer = csv.writer(csvfile)
        writer.writerow(['Block', 'Sample_In_Block', 'Global_Sample', 'Voltage_V', 'Timestamp'])
    logger.info("CSV file initialized with headers")

    total_start_time = time.time()
    global_sample_index = 0

    print(f"\n=== Iniciando adquisición de {num_blocks if not infinite_mode else '∞ (indefinido)'} bloques de {samples_per_count} muestras cada uno ===")
    if infinite_mode:
        print(f"📊 Modo indefinido: continuará hasta interrupción manual")
        print(f"⏱️ Tiempo estimado: indefinido")
        total_samples_expected = float('inf')  # Infinito
    else:
        total_samples_expected = num_blocks * samples_per_count
        # Estimación de tiempo basada en NPLCycles
        nplc_factor = float(nplc_cycles) if isinstance(nplc_cycles, (int, float)) else 10
        estimated_time_per_sample = nplc_factor * 0.0001  # Factor aproximado
        estimated_time = num_blocks * samples_per_count * estimated_time_per_sample
        print(f"📊 Total esperado: {total_samples_expected:,} muestras")
        print(f"⏱️ Tiempo estimado: {estimated_time:.1f} segundos ({estimated_time/60:.1f} minutos)")

    # Confirmar inicio
    confirm = input("¿Desea continuar? (y/n): ").strip().lower()
    if confirm not in ['y', 'yes', 's', 'si', '']:
        print("❌ Adquisición cancelada")
        logger.info("Acquisition cancelled by user")
        exit(0)
    
    if infinite_mode:
        logger.info(f"Starting infinite acquisition of {samples_per_count} samples per block")
        logger.info("Acquisition will continue until manually interrupted")
    else:
        logger.info(f"Starting acquisition of {num_blocks} blocks of {samples_per_count} samples each")
        logger.info(f"Expected total: {total_samples_expected} samples, estimated time: {estimated_time:.1f}s")

    # Iniciar thread de interrupción
    if KEYBOARD_AVAILABLE:
        interruption_thread = threading.Thread(target=check_for_interruption, daemon=True)
        interruption_thread.start()
        logger.info("Interruption thread started")
    else:
        print("\n💡 Para interrumpir: presiona Ctrl+C en la terminal")
        logger.info("Keyboard interruption not available - use Ctrl+C to interrupt")

    # Bucle principal de adquisición
    block_num = 0
    while (infinite_mode and not stop_acquisition) or (not infinite_mode and block_num < num_blocks):
        block_num += 1

        # Verificar si se solicitó interrupción
        if stop_acquisition:
            if infinite_mode:
                print(f"\n🛑 Adquisición interrumpida en el bloque {block_num} (modo indefinido)")
                logger.warning(f"Acquisition stopped at block {block_num} (infinite mode)")
            else:
                progress_percent = ((block_num - 1) / num_blocks) * 100
                print(f"\n🛑 Adquisición interrumpida en el bloque {block_num}/{num_blocks} ({progress_percent:.1f}%)")
                logger.warning(f"Acquisition stopped at block {block_num}/{num_blocks} ({progress_percent:.1f}%)")
            break

        block_start_time = time.time()
        if infinite_mode:
            print(f"\n--- Bloque {block_num} (modo indefinido) ---")
            logger.info(f"Starting block {block_num} (infinite mode)")
        else:
            progress_percent = ((block_num - 1) / num_blocks) * 100
            print(f"\n--- Bloque {block_num}/{num_blocks} ({progress_percent:.1f}%) ---")
            logger.info(f"Starting block {block_num}/{num_blocks} ({progress_percent:.1f}%)")

        try:
            # Set sample count for this block
            inst.write(f'SAMPle:COUNt {samples_per_count}')
            logger.debug(f"Sample count set to {samples_per_count} for block {block_num}")

            # Initiate the measurement
            inst.write('INITiate:IMMediate')
            logger.debug(f"Initiated measurement for block {block_num}")

            # Wait for measurement completion with polling
            print(f"Esperando completación del bloque {block_num}...")
            poll_start = time.time()
            poll_count = 0

            while True:
                poll_count += 1
                opc_response = inst.query('*OPC?').strip()

                if opc_response == '1':
                    break

                elapsed = time.time() - poll_start
                if elapsed > 30:  # Timeout after 30 seconds
                    raise TimeoutError(f"Timeout esperando completación del bloque {block_num}")

                time.sleep(0.1)  # Poll every 100ms

            block_acquisition_time = time.time() - poll_start
            logger.info(f"Block {block_num} completed in {block_acquisition_time:.3f}s after {poll_count} polls")

            # Fetch the readings
            readings_str = inst.query('FETCh?')
            logger.debug(f"Fetched readings string for block {block_num}")

            # Parse the readings
            block_readings = [float(r) for r in readings_str.strip().split(',')]
            logger.info(f"Parsed {len(block_readings)} readings for block {block_num}")

            if len(block_readings) != samples_per_count:
                logger.warning(f"Expected {samples_per_count} readings, got {len(block_readings)} for block {block_num}")

            # Add to global readings list
            readings.extend(block_readings)

            # Save block data to CSV immediately
            block_timestamp = datetime.now().isoformat()
            with open(csv_filename, 'a', newline='') as csvfile:
                writer = csv.writer(csvfile)
                for i, voltage in enumerate(block_readings, 1):
                    global_sample_index += 1
                    writer.writerow([block_num, i, global_sample_index, voltage, block_timestamp])

            block_total_time = time.time() - block_start_time
            block_sps = len(block_readings) / block_acquisition_time if block_acquisition_time > 0 else 0

            print(f"✓ Bloque {block_num} completado: {len(block_readings)} muestras en {block_total_time:.3f}s")
            print(f"  SPS calculado: {block_sps:.1f}")
            logger.info(f"Block {block_num} saved: {len(block_readings)} samples, {block_sps:.1f} SPS")

        except Exception as e:
            logger.error(f"Error en bloque {block_num}: {e}")
            print(f"✗ Error en bloque {block_num}: {e}")
            continue

    # Detener thread de interrupción
    if KEYBOARD_AVAILABLE:
        stop_acquisition = True
        interruption_thread.join(timeout=1.0)  # Esperar máximo 1 segundo
        logger.info("Interruption thread stopped")

    # Calcular estadísticas finales
    total_time = time.time() - total_start_time
    total_samples = len(readings)
    overall_sps = total_samples / total_time if total_time > 0 else 0

    # Calcular estadísticas avanzadas
    if readings:
        advanced_stats = calculate_advanced_statistics(readings)
        print(f"\n📊 Estadísticas Avanzadas:")
        print(f"  • Media: {advanced_stats.get('mean', 0):.6f} V")
        print(f"  • Desviación estándar: {advanced_stats.get('std', 0):.6f} V")
        print(f"  • Varianza: {advanced_stats.get('variance', 0):.8f} V²")
        print(f"  • Desviación Media Absoluta: {advanced_stats.get('mad', 0):.6f} V")
        print(f"  • Rango: {advanced_stats.get('range', 0):.6f} V")
        if 'cv' in advanced_stats:
            print(f"  • Coeficiente de variación: {advanced_stats['cv']:.2f}%")
        if 'autocorr_lag1' in advanced_stats:
            print(f"  • Autocorrelación (lag 1): {advanced_stats['autocorr_lag1']:.4f}")
        if 'time_correlation' in advanced_stats:
            print(f"  • Correlación temporal: {advanced_stats['time_correlation']:.4f}")

    # Determinar si fue completado o interrumpido
    completion_status = "completada" if not stop_acquisition else "interrumpida"
    completion_icon = "✅" if not stop_acquisition else "🛑"

    print(f"\n=== Adquisición {completion_status} ===")
    print(f"{completion_icon} Total de muestras: {total_samples}")
    print(f"⏱️ Tiempo total: {total_time:.3f} segundos")
    print(f"📊 SPS promedio: {overall_sps:.1f}")
    print(f"💾 Datos guardados en: {csv_filename}")

    if stop_acquisition:
        blocks_completed = block_num - 1  # block_num es el último que intentó ejecutar
        progress_percent = (blocks_completed / num_blocks) * 100
        print(f"📋 Bloques completados: {blocks_completed}/{num_blocks} ({progress_percent:.1f}%)")

    logger.info(f"Acquisition {completion_status}: {total_samples} total samples, {overall_sps:.1f} SPS average")

    # # Verify final instrument state
    # if 'inst' in locals() and not check_instrument_errors(inst):
    #     logger.warning("Errors detected at end of acquisition")

except KeyboardInterrupt:
    stop_acquisition = True
    logger.warning("Acquisition interrupted by user (Ctrl+C)")
    print("\n🛑 Interrupción por Ctrl+C detectada!")
    print("Los datos adquiridos hasta ahora serán guardados y graficados.")

    # Calcular estadísticas finales si hay datos
    if 'total_start_time' in locals() and readings:
        total_time = time.time() - total_start_time
        total_samples = len(readings)
        overall_sps = total_samples / total_time if total_time > 0 else 0

        completion_status = "interrumpida"
        completion_icon = "🛑"

        print(f"\n=== Adquisición {completion_status} ===")
        print(f"{completion_icon} Total de muestras: {total_samples}")
        print(f"⏱️ Tiempo transcurrido: {total_time:.3f} segundos")
        print(f"📊 SPS promedio: {overall_sps:.1f}")
        if 'csv_filename' in locals():
            print(f"💾 Datos guardados en: {csv_filename}")

        if 'num_blocks' in locals():
            blocks_completed = block_num - 1 if 'block_num' in locals() else 0
            progress_percent = (blocks_completed / num_blocks) * 100 if num_blocks > 0 else 0
            print(f"📋 Bloques completados: {blocks_completed}/{num_blocks} ({progress_percent:.1f}%)")

        logger.info(f"Acquisition {completion_status}: {total_samples} total samples, {overall_sps:.1f} SPS average")
finally:
    # Close the connection and resource manager
    try:
        if 'inst' in locals():
            inst.close()
            logger.info("Instrument connection closed")
        if 'rm' in locals():
            rm.close()
            logger.info("Resource manager closed")
    except Exception as e:
        logger.error(f"Error closing resources: {e}")
        print(f"Error cerrando recursos: {e}")

# Generar gráfica si hay datos (se ejecuta siempre, incluso después de interrupción)
if 'csv_filename' in locals() and readings:
    print("\n=== Generando gráfica ===")
    logger.info("Generating plot")

    try:
        # Read data from CSV for plotting
        plot_data = []
        with open(csv_filename, 'r') as csvfile:
            reader = csv.DictReader(csvfile)
            for row in reader:
                plot_data.append({
                    'global_sample': int(row['Global_Sample']),
                    'voltage': float(row['Voltage_V']),
                    'block': int(row['Block'])
                })

        if plot_data:
            sample_indices = [d['global_sample'] for d in plot_data]
            voltages = [d['voltage'] for d in plot_data]

            if no_stats:
                # Gráfica básica: solo serie temporal y histograma simple
                fig = plt.figure(figsize=(12, 5))

                # Subplot 1: Serie temporal básica
                plt.subplot(1, 2, 1)
                plt.plot(sample_indices, voltages, 'b-', alpha=0.7, linewidth=1)
                plt.xlabel('Muestra Global')
                plt.ylabel('Voltaje (V)')
                plt.title(f'Datos de Voltaje - {len(plot_data)} muestras')
                plt.grid(True, alpha=0.3)

                # Subplot 2: Histograma básico
                plt.subplot(1, 2, 2)
                plt.hist(voltages, bins=30, alpha=0.7, color='skyblue', edgecolor='black')
                plt.xlabel('Voltaje (V)')
                plt.ylabel('Frecuencia')
                plt.title('Distribución de Voltajes')
                plt.grid(True, alpha=0.3)

                # REMOVED: plt.tight_layout(), save and show moved outside if/else
            else:
                # Calcular estadísticas avanzadas para la gráfica completa
                stats = calculate_advanced_statistics(voltages)

                # Crear figura con más subplots
                fig = plt.figure(figsize=(16, 12))

                # Subplot 1: Serie temporal completa
                plt.subplot(3, 2, 1)
                plt.plot(sample_indices, voltages, 'b-', alpha=0.7, linewidth=1, label='Datos')
                plt.axhline(y=stats.get('mean', 0), color='r', linestyle='--', alpha=0.8,
                           label=f'Media: {stats.get("mean", 0):.6f}V')
                plt.axhline(y=stats.get('mean', 0) + stats.get('std', 0), color='orange', linestyle=':', alpha=0.6,
                           label=f'+1σ: {stats.get("mean", 0) + stats.get("std", 0):.6f}V')
                plt.axhline(y=stats.get('mean', 0) - stats.get('std', 0), color='orange', linestyle=':', alpha=0.6,
                           label=f'-1σ: {stats.get("mean", 0) - stats.get("std", 0):.6f}V')
                plt.xlabel('Muestra Global')
                plt.ylabel('Voltaje (V)')
                plt.title(f'Serie Temporal Completa - {len(plot_data)} muestras')
                plt.grid(True, alpha=0.3)
                plt.legend()
                # plt.tight_layout()  # REMOVED: This should be at the end after all subplots are created

            # Subplot 2: Histograma con distribución
            plt.subplot(3, 2, 2)
            if NUMPY_AVAILABLE:
                # Histograma con KDE si numpy y scipy están disponibles
                plt.hist(voltages, bins=50, alpha=0.7, color='skyblue', edgecolor='black', density=True, label='Histograma')

                # Línea de densidad usando scipy
                if SCIPY_AVAILABLE:
                    try:
                        kde = scipy_stats.gaussian_kde(voltages)
                        x_range = np.linspace(min(voltages), max(voltages), 100)
                        plt.plot(x_range, kde(x_range), 'r-', linewidth=2, label='Densidad KDE')
                    except Exception as e:
                        logger.warning(f"No se pudo calcular KDE: {e}")
                else:
                    plt.hist(voltages, bins=30, alpha=0.7, color='skyblue', edgecolor='black', label='Histograma')
            else:
                plt.hist(voltages, bins=30, alpha=0.7, color='skyblue', edgecolor='black', label='Histograma')

            plt.axvline(x=stats.get('mean', 0), color='red', linestyle='--', linewidth=2,
                       label=f'Media: {stats.get("mean", 0):.6f}V')
            plt.xlabel('Voltaje (V)')
            plt.ylabel('Frecuencia')
            plt.title('Distribución de Voltajes')
            plt.grid(True, alpha=0.3)
            plt.legend()

            # Subplot 3: Estadísticas por bloque con error bars mejorados
            plt.subplot(3, 2, 3)
            blocks = sorted(list(set(d['block'] for d in plot_data)))
            block_means = []
            block_stds = []
            block_mads = []
            block_variances = []

            for block in blocks:
                block_voltages = [d['voltage'] for d in plot_data if d['block'] == block]
                if block_voltages:
                    if NUMPY_AVAILABLE:
                        block_array = np.array(block_voltages)
                        mean_val = np.mean(block_array)
                        std_val = np.std(block_array, ddof=1)
                        mad_val = np.mean(np.abs(block_array - mean_val))
                        var_val = np.var(block_array, ddof=1)
                    else:
                        mean_val = sum(block_voltages) / len(block_voltages)
                        var_val = sum((x - mean_val) ** 2 for x in block_voltages) / (len(block_voltages) - 1) if len(block_voltages) > 1 else 0
                        std_val = var_val ** 0.5
                        mad_val = sum(abs(x - mean_val) for x in block_voltages) / len(block_voltages)

                    block_means.append(mean_val)
                    block_stds.append(std_val)
                    block_mads.append(mad_val)
                    block_variances.append(var_val)

            # Plot con múltiples métricas
            plt.errorbar(blocks, block_means, yerr=block_stds, fmt='ro-', capsize=3, alpha=0.7, label='Media ± σ')
            plt.plot(blocks, [m + mad for m, mad in zip(block_means, block_mads)], 'b--', alpha=0.6, label='Media + MAD')
            plt.plot(blocks, [m - mad for m, mad in zip(block_means, block_mads)], 'b--', alpha=0.6, label='Media - MAD')
            plt.xlabel('Número de Bloque')
            plt.ylabel('Voltaje (V)')
            plt.title('Estadísticas por Bloque (Media, σ, MAD)')
            plt.grid(True, alpha=0.3)
            plt.legend()

            # Subplot 4: Autocorrelación y tendencias
            plt.subplot(3, 2, 4)
            if NUMPY_AVAILABLE and len(voltages) > 10:
                # Calcular autocorrelación
                max_lag = min(50, len(voltages) // 4)  # Máximo lag razonable
                autocorr = []
                lags = []

                for lag in range(1, max_lag + 1):
                    if len(voltages) > lag:
                        corr = np.corrcoef(voltages[:-lag], voltages[lag:])[0, 1]
                        autocorr.append(corr)
                        lags.append(lag)

                plt.plot(lags, autocorr, 'g-o', alpha=0.7, markersize=3)
                plt.axhline(y=0, color='black', linestyle='-', alpha=0.3)
                plt.xlabel('Lag (muestras)')
                plt.ylabel('Autocorrelación')
                plt.title('Función de Autocorrelación')
                plt.grid(True, alpha=0.3)

                # Agregar línea de significancia aproximada
                n = len(voltages)
                significance_level = 1.96 / np.sqrt(n)  # 95% confidence
                plt.axhline(y=significance_level, color='red', linestyle='--', alpha=0.5, label='95% significancia')
                plt.axhline(y=-significance_level, color='red', linestyle='--', alpha=0.5)
                plt.legend()
            else:
                plt.text(0.5, 0.5, 'Datos insuficientes\npara autocorrelación',
                        transform=plt.gca().transAxes, ha='center', va='center', fontsize=12)
                plt.title('Autocorrelación (Datos insuficientes)')

            # Subplot 5: Análisis de estabilidad (moving statistics)
            plt.subplot(3, 2, 5)
            if len(voltages) > 100:  # Solo si hay suficientes datos
                window_size = max(50, len(voltages) // 20)  # Ventana adaptativa
                moving_mean = []
                moving_std = []
                positions = []

                for i in range(window_size, len(voltages), window_size // 2):
                    window = voltages[i-window_size:i]
                    if len(window) > 10:
                        if NUMPY_AVAILABLE:
                            moving_mean.append(np.mean(window))
                            moving_std.append(np.std(window, ddof=1))
                        else:
                            mean_val = sum(window) / len(window)
                            var_val = sum((x - mean_val) ** 2 for x in window) / (len(window) - 1) if len(window) > 1 else 0
                            moving_mean.append(mean_val)
                            moving_std.append(var_val ** 0.5)
                        positions.append(i)

                if moving_mean:
                    plt.plot(positions, moving_mean, 'purple', linewidth=2, label='Media móvil')
                    plt.fill_between(positions,
                                   [m - s for m, s in zip(moving_mean, moving_std)],
                                   [m + s for m, s in zip(moving_mean, moving_std)],
                                   alpha=0.3, color='purple', label='±σ móvil')
                    plt.xlabel('Posición en la serie')
                    plt.ylabel('Voltaje (V)')
                    plt.title(f'Estabilidad (Ventana: {window_size} muestras)')
                    plt.grid(True, alpha=0.3)
                    plt.legend()
                else:
                    plt.text(0.5, 0.5, 'Datos insuficientes\npara análisis de estabilidad',
                            transform=plt.gca().transAxes, ha='center', va='center', fontsize=12)
            else:
                plt.text(0.5, 0.5, 'Datos insuficientes\npara análisis de estabilidad',
                        transform=plt.gca().transAxes, ha='center', va='center', fontsize=12)
                plt.title('Análisis de Estabilidad')

            # Subplot 6: Resumen estadístico
            plt.subplot(3, 2, 6)
            plt.axis('off')  # Ocultar ejes

            # Crear tabla de estadísticas
            stats_text = ".2e" if abs(stats.get('variance', 0)) < 0.001 else ".6f"
            summary_text = ".1f" if abs(stats.get('variance', 0)) < 0.001 else ".6f"

            stats_info = [
                f"Estadísticas del Conjunto de Datos",
                f"=" * 35,
                f"",
                f"Número de muestras: {len(voltages):,}",
                f"Media: {stats.get('mean', 0):.6f} V",
                f"Desviación estándar: {stats.get('std', 0):.6f} V",
                f"Varianza: {stats.get('variance', 0):{stats_text}} V²",
                f"Desviación Media Absoluta: {stats.get('mad', 0):.6f} V",
                f"Rango: {stats.get('range', 0):.6f} V",
                f"Mínimo: {stats.get('min', 0):.6f} V",
                f"Máximo: {stats.get('max', 0):.6f} V",
            ]

            if 'cv' in stats:
                stats_info.append(f"Coeficiente de variación: {stats['cv']:.2f}%")
            if 'skewness' in stats:
                stats_info.append(f"Asimetría: {stats['skewness']:.4f}")
            if 'kurtosis' in stats:
                stats_info.append(f"Curtosis: {stats['kurtosis']:.4f}")
            if 'autocorr_lag1' in stats:
                stats_info.append(f"Autocorrelación (lag 1): {stats['autocorr_lag1']:.4f}")
            if 'time_correlation' in stats:
                trend_desc = "tendencia creciente" if stats['time_correlation'] > 0.1 else "tendencia decreciente" if stats['time_correlation'] < -0.1 else "sin tendencia clara"
                stats_info.append(f"Correlación temporal: {stats['time_correlation']:.4f} ({trend_desc})")

            plt.text(0.05, 0.95, '\n'.join(stats_info), transform=plt.gca().transAxes,
                    fontsize=9, verticalalignment='top', fontfamily='monospace',
                    bbox=dict(boxstyle="round,pad=0.5", facecolor="lightgray", alpha=0.8))

            # Apply tight layout after all subplots are created
            plt.tight_layout()

            # Save plot
            plot_filename = f'voltage_analysis_{experiment_label}_{datetime.now().strftime("%Y%m%d_%H%M%S")}.png'
            plt.savefig(plot_filename, dpi=300, bbox_inches='tight')
            print(f"Gráfica guardada como: {plot_filename}")
            logger.info(f"Analysis plot saved as {plot_filename}")

            plt.show()

    except Exception as e:
        logger.error(f"Error generating plot: {e}")
        print(f"Error generando gráfica: {e}")

print("\n=== Proceso completado ===")
logger.info("Process completed successfully")