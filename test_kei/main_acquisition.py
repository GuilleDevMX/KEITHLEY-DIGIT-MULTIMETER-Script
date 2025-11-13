#!/usr/bin/env python3
"""
Módulo principal para adquisición de datos sincronizada Keithley-Alicat

Este módulo proporciona una interfaz completa para ejecutar experimentos de respuesta
a pulsos de presión con adquisición sincronizada de voltaje y presión.

Autor: GuilleDevMX
Fecha: Noviembre 2025
"""

import sys
import os
import time
import threading
import logging
import signal
from pathlib import Path

# Agregar el directorio actual al path para importar módulos locales
current_dir = Path(__file__).parent
sys.path.insert(0, str(current_dir))

# Importar funciones del módulo de adquisición
from response_single_pulse import (
    acquisition_loop,
    detener_adquisicion,
    pausar_reanudar_adquisicion,
    KeithleyAcquisition,
    stability_setpoint
)

# =============================================================================
# CONFIGURACIÓN GLOBAL
# =============================================================================

# Variables globales requeridas por acquisition_loop
acquisition_running = False
acquisition_paused = False
logger = None
ser_alicat_global = None
keithley_acquirer_global = None
thread_acquisition = None

# Configuración por defecto del Keithley
DEFAULT_KEITHLEY_CONFIG = {
    'output_dir': 'lecturas',
    'experiment_label': 'adquisicion_presion',
    'nplc_cycles': 1,           # Ciclos NPLC (precisión: 0.001 = alta precisión)
    'samples_per_count': 1,         # Muestras por bloque
    'num_blocks': 50,               # Número de bloques (si no infinito)
    'infinite_mode': False,         # False = modo finito, True = infinito
    'quiet': False                  # False = mostrar prompts de confirmación
}

# Configuración por defecto de parámetros de adquisición
DEFAULT_ACQUISITION_PARAMS = {
    'setpoint_inicial': 0.0,         # Presión inicial (kPa)
    'setpoint_final': 6.86,          # Presión final (kPa)
    'setpoint_intervalo': 10.0,      # Tiempo entre cambios de setpoint (segundos)
    'num_puntos_intermedios': 3,     # Puntos intermedios en cada rampa
    'num_ciclos': 1,                 # Número de ciclos completos
    'intermediate_mode': 'auto',     # 'auto' o 'manual'
    'custom_points_text': '[0, 1.5, 3.0, 4.5, 6.86]',  # Puntos manuales
    'enable_stability': False,        # Habilitar estabilización de presión
    'stability_time': 15.0,          # Tiempo máximo para estabilizar (segundos)
    'file_label': 'ExperimentoPresion'  # Prefijo para archivos CSV
}

# =============================================================================
# FUNCIONES DE CONFIGURACIÓN
# =============================================================================

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

def validate_configuration(keithley_config, acquisition_params):
    """
    Valida la configuración antes de iniciar la adquisición

    Args:
        keithley_config: Configuración del Keithley
        acquisition_params: Parámetros de adquisición

    Returns:
        bool: True si la configuración es válida
    """
    errors = []

    # Validar configuración del Keithley
    required_keithley_keys = ['output_dir', 'experiment_label', 'nplc_cycles',
                             'samples_per_count', 'infinite_mode', 'quiet']
    for key in required_keithley_keys:
        if key not in keithley_config:
            errors.append(f"Falta clave requerida en configuración Keithley: {key}")

    if keithley_config.get('nplc_cycles', 0) <= 0:
        errors.append("nplc_cycles debe ser mayor que 0")

    if keithley_config.get('samples_per_count', 0) <= 0:
        errors.append("samples_per_count debe ser mayor que 0")

    # Validar parámetros de adquisición
    required_param_keys = ['setpoint_inicial', 'setpoint_final', 'setpoint_intervalo',
                          'num_puntos_intermedios', 'num_ciclos', 'intermediate_mode']
    for key in required_param_keys:
        if key not in acquisition_params:
            errors.append(f"Falta clave requerida en parámetros: {key}")

    if acquisition_params.get('setpoint_inicial', 0) < 0:
        errors.append("setpoint_inicial no puede ser negativo")

    if acquisition_params.get('setpoint_final', 0) < 0:
        errors.append("setpoint_final no puede ser negativo")

    if acquisition_params.get('setpoint_intervalo', 0) <= 0:
        errors.append("setpoint_intervalo debe ser mayor que 0")

    if acquisition_params.get('num_ciclos', 0) <= 0:
        errors.append("num_ciclos debe ser mayor que 0")

    if acquisition_params.get('intermediate_mode') not in ['auto', 'manual']:
        errors.append("intermediate_mode debe ser 'auto' o 'manual'")

    # Mostrar errores si los hay
    if errors:
        logger.error("Errores de configuración encontrados:")
        for error in errors:
            logger.error(f"  - {error}")
        return False

    return True

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

        # Probar conexión con Alicat
        logger.info("Probando conexión con Alicat...")
        import serial
        test_alicat = serial.Serial(port="COM5", baudrate=115200, timeout=1)
        time.sleep(0.5)
        if test_alicat.is_open:
            logger.info("✅ Conexión con Alicat exitosa")
            test_alicat.close()
        else:
            logger.warning("⚠️ No se pudo verificar conexión con Alicat")

        return True

    except Exception as e:
        logger.error(f"❌ Error en conexiones: {e}")
        return False

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
    logger.info(f"  Presión - Inicial: {acquisition_params['setpoint_inicial']} kPa")
    logger.info(f"  Presión - Final: {acquisition_params['setpoint_final']} kPa")
    logger.info(f"  Presión - Ciclos: {acquisition_params['num_ciclos']}")
    logger.info(f"  Presión - Intervalo: {acquisition_params['setpoint_intervalo']} s")
    logger.info(f"  Estabilización: {'Habilitada' if acquisition_params['enable_stability'] else 'Deshabilitada'}")

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

# =============================================================================
# FUNCIONES DE CONFIGURACIÓN INTERACTIVA
# =============================================================================

def interactive_configuration():
    """
    Configuración interactiva del experimento

    Returns:
        tuple: (keithley_config, acquisition_params)
    """
    print("\n" + "="*60)
    print("CONFIGURACIÓN INTERACTIVA DEL EXPERIMENTO")
    print("="*60)

    # Configuración del Keithley
    print("\n📊 CONFIGURACIÓN DEL KEITHLEY:")
    keithley_config = DEFAULT_KEITHLEY_CONFIG.copy()

    keithley_config['output_dir'] = input(f"Directorio de salida [{keithley_config['output_dir']}]: ").strip() or keithley_config['output_dir']
    keithley_config['experiment_label'] = input(f"Etiqueta del experimento [{keithley_config['experiment_label']}]: ").strip() or keithley_config['experiment_label']

    try:
        nplc = input(f"Ciclos NPLC (precisión) [{keithley_config['nplc_cycles']}]: ").strip()
        keithley_config['nplc_cycles'] = int(nplc) if nplc else keithley_config['nplc_cycles']
    except ValueError:
        print("Valor inválido, usando valor por defecto")

    try:
        samples = input(f"Muestras por bloque [{keithley_config['samples_per_count']}]: ").strip()
        keithley_config['samples_per_count'] = int(samples) if samples else keithley_config['samples_per_count']
    except ValueError:
        print("Valor inválido, usando valor por defecto")

    infinite = input(f"Modo infinito (s/n) [{'s' if keithley_config['infinite_mode'] else 'n'}]: ").strip().lower()
    keithley_config['infinite_mode'] = infinite in ['s', 'si', 'y', 'yes', 'true']

    if not keithley_config['infinite_mode']:
        try:
            blocks = input(f"Número de bloques [{keithley_config['num_blocks']}]: ").strip()
            keithley_config['num_blocks'] = int(blocks) if blocks else keithley_config['num_blocks']
        except ValueError:
            print("Valor inválido, usando valor por defecto")

    # Configuración de parámetros de adquisición
    print("\n🔧 CONFIGURACIÓN DE PARÁMETROS DE ADQUISICIÓN:")
    acquisition_params = DEFAULT_ACQUISITION_PARAMS.copy()

    try:
        acquisition_params['setpoint_inicial'] = float(input(f"Presión inicial (kPa) [{acquisition_params['setpoint_inicial']}]: ").strip() or acquisition_params['setpoint_inicial'])
    except ValueError:
        print("Valor inválido, usando valor por defecto")

    try:
        acquisition_params['setpoint_final'] = float(input(f"Presión final (kPa) [{acquisition_params['setpoint_final']}]: ").strip() or acquisition_params['setpoint_final'])
    except ValueError:
        print("Valor inválido, usando valor por defecto")

    try:
        acquisition_params['setpoint_intervalo'] = float(input(f"Intervalo entre setpoints (s) [{acquisition_params['setpoint_intervalo']}]: ").strip() or acquisition_params['setpoint_intervalo'])
    except ValueError:
        print("Valor inválido, usando valor por defecto")

    try:
        acquisition_params['num_puntos_intermedios'] = int(input(f"Puntos intermedios por rampa [{acquisition_params['num_puntos_intermedios']}]: ").strip() or acquisition_params['num_puntos_intermedios'])
    except ValueError:
        print("Valor inválido, usando valor por defecto")

    try:
        acquisition_params['num_ciclos'] = int(input(f"Número de ciclos [{acquisition_params['num_ciclos']}]: ").strip() or acquisition_params['num_ciclos'])
    except ValueError:
        print("Valor inválido, usando valor por defecto")

    mode = input(f"Modo intermedio (auto/manual) [{acquisition_params['intermediate_mode']}]: ").strip().lower()
    if mode in ['auto', 'manual']:
        acquisition_params['intermediate_mode'] = mode

    if acquisition_params['intermediate_mode'] == 'manual':
        acquisition_params['custom_points_text'] = input(f"Puntos personalizados [{acquisition_params['custom_points_text']}]: ").strip() or acquisition_params['custom_points_text']

    stability = input(f"Habilitar estabilización (s/n) [{'s' if acquisition_params['enable_stability'] else 'n'}]: ").strip().lower()
    acquisition_params['enable_stability'] = stability in ['s', 'si', 'y', 'yes', 'true']

    if acquisition_params['enable_stability']:
        try:
            acquisition_params['stability_time'] = float(input(f"Tiempo de estabilización (s) [{acquisition_params['stability_time']}]: ").strip() or acquisition_params['stability_time'])
        except ValueError:
            print("Valor inválido, usando valor por defecto")

    acquisition_params['file_label'] = input(f"Etiqueta del archivo [{acquisition_params['file_label']}]: ").strip() or acquisition_params['file_label']

    return keithley_config, acquisition_params

# =============================================================================
# FUNCIÓN MAIN
# =============================================================================

def main():
    """
    Función principal del programa
    """
    import argparse

    parser = argparse.ArgumentParser(
        description="Adquisición sincronizada Keithley-Alicat para experimentos de presión",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Ejemplos de uso:

  # Configuración interactiva
  python main_acquisition.py --interactive

  # Configuración por defecto
  python main_acquisition.py --default

  # Configuración personalizada
  python main_acquisition.py --presion-inicial 0 --presion-final 5.0 --ciclos 3 --intervalo 20

  # Modo infinito
  python main_acquisition.py --infinite --presion-final 10.0
        """
    )

    # Argumentos de configuración general
    parser.add_argument('--interactive', action='store_true',
                       help='Configuración interactiva del experimento')
    parser.add_argument('--default', action='store_true',
                       help='Usar configuración por defecto')
    parser.add_argument('--test-connections', action='store_true', default=True,
                       help='Probar conexiones antes de iniciar (por defecto: True)')
    parser.add_argument('--no-test-connections', action='store_false', dest='test_connections',
                       help='No probar conexiones antes de iniciar')

    # Argumentos de configuración del Keithley
    keithley_group = parser.add_argument_group('Configuración Keithley')
    keithley_group.add_argument('--output-dir', default='lecturas',
                               help='Directorio de salida para datos')
    keithley_group.add_argument('--experiment-label', default='adquisicion_presion',
                               help='Etiqueta del experimento')
    keithley_group.add_argument('--nplc', type=int, default=10,
                               help='Ciclos NPLC (precisión)')
    keithley_group.add_argument('--samples-per-block', type=int, default=1000,
                               help='Muestras por bloque')
    keithley_group.add_argument('--infinite', action='store_true',
                               help='Modo de adquisición infinita')
    keithley_group.add_argument('--num-blocks', type=int, default=50,
                               help='Número de bloques (solo en modo finito)')

    # Argumentos de configuración de presión
    pressure_group = parser.add_argument_group('Configuración de Presión')
    pressure_group.add_argument('--presion-inicial', type=float, default=0.0,
                               help='Presión inicial (kPa)')
    pressure_group.add_argument('--presion-final', type=float, default=6.86,
                               help='Presión final (kPa)')
    pressure_group.add_argument('--intervalo', type=float, default=30.0,
                               help='Intervalo entre cambios de setpoint (segundos)')
    pressure_group.add_argument('--puntos-intermedios', type=int, default=5,
                               help='Puntos intermedios por rampa')
    pressure_group.add_argument('--ciclos', type=int, default=2,
                               help='Número de ciclos completos')
    pressure_group.add_argument('--modo-intermedio', choices=['auto', 'manual'], default='auto',
                               help='Modo de puntos intermedios')
    pressure_group.add_argument('--puntos-personalizados', default='[0, 1.5, 3.0, 4.5, 6.86]',
                               help='Puntos personalizados (solo en modo manual)')
    pressure_group.add_argument('--estabilidad', action='store_true', default=True,
                               help='Habilitar estabilización de presión')
    pressure_group.add_argument('--no-estabilidad', action='store_false', dest='estabilidad',
                               help='Deshabilitar estabilización de presión')
    pressure_group.add_argument('--tiempo-estabilidad', type=float, default=15.0,
                               help='Tiempo máximo de estabilización (segundos)')
    pressure_group.add_argument('--file-label', default='ExperimentoPresion',
                               help='Prefijo para archivos CSV')

    # Argumentos de logging
    parser.add_argument('--log-level', choices=['DEBUG', 'INFO', 'WARNING', 'ERROR'],
                       default='INFO', help='Nivel de logging')
    parser.add_argument('--log-file',
                       help='Archivo para guardar logs')

    args = parser.parse_args()

    # Configurar logging
    log_level = getattr(logging, args.log_level.upper())
    setup_logging(level=log_level, log_file=args.log_file)

    # Determinar modo de configuración
    if args.interactive:
        logger.info("Modo configuración interactiva")
        keithley_config, acquisition_params = interactive_configuration()
    elif args.default:
        logger.info("Usando configuración por defecto")
        keithley_config = DEFAULT_KEITHLEY_CONFIG.copy()
        acquisition_params = DEFAULT_ACQUISITION_PARAMS.copy()
    else:
        logger.info("Usando configuración por argumentos de línea de comandos")
        # Construir configuración desde argumentos
        keithley_config = {
            'output_dir': args.output_dir,
            'experiment_label': args.experiment_label,
            'nplc_cycles': args.nplc,
            'samples_per_count': args.samples_per_block,
            'num_blocks': args.num_blocks,
            'infinite_mode': args.infinite,
            'quiet': False
        }

        acquisition_params = {
            'setpoint_inicial': args.presion_inicial,
            'setpoint_final': args.presion_final,
            'setpoint_intervalo': args.intervalo,
            'num_puntos_intermedios': args.puntos_intermedios,
            'num_ciclos': args.ciclos,
            'intermediate_mode': args.modo_intermedio,
            'custom_points_text': args.puntos_personalizados,
            'enable_stability': args.estabilidad,
            'stability_time': args.tiempo_estabilidad,
            'file_label': args.file_label
        }

    # Ejecutar experimento
    success = run_acquisition_experiment(
        keithley_config=keithley_config,
        acquisition_params=acquisition_params,
        test_connections=args.test_connections
    )

    # Código de salida
    sys.exit(0 if success else 1)

if __name__ == "__main__":
    main()