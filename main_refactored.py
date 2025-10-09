#!/usr/bin/env python3
"""
Sistema de adquisición de datos Keithley - Versión Modular
"""
import sys
import logging
from datetime import datetime

# Importar módulos locales
from config import KeithleyConfig
from acquisition import KeithleyAcquisition, KeithleyError
from analysis import StatisticalAnalyzer
from plotting import KeithleyPlotter


def setup_logging(config: dict) -> logging.Logger:
    """Configura el sistema de logging"""
    log_filename = f'keithley_acquisition_{datetime.now().strftime("%Y%m%d")}.log'
    log_filepath = f"{config['output_dir']}/{log_filename}"

    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_filepath),
            logging.StreamHandler()
        ]
    )

    logger = logging.getLogger(__name__)

    # Log de configuración inicial
    logger.info(f"Experiment label: {config['experiment_label']}")
    logger.info(f"Samples per count: {config['samples_per_count']}")
    logger.info(f"NPLCycles: {config['nplc_cycles']}")
    logger.info(f"Number of blocks: {'infinite' if config['infinite_mode'] else config['num_blocks']}")
    logger.info(f"Statistics plots: {'disabled' if config['no_stats'] else 'enabled'}")

    return logger


def check_dependencies():
    """Verifica y reporta dependencias disponibles"""
    dependencies = {}

    # NumPy
    try:
        import numpy
        dependencies['numpy'] = True
        print(f"✅ NumPy {numpy.__version__} disponible")
    except ImportError:
        dependencies['numpy'] = False
        print("⚠️ NumPy no disponible - estadísticas limitadas")

    # SciPy
    try:
        import scipy
        dependencies['scipy'] = True
        print(f"✅ SciPy {scipy.__version__} disponible")
    except ImportError:
        dependencies['scipy'] = False
        print("⚠️ SciPy no disponible - análisis KDE limitado")

    # Matplotlib
    try:
        import matplotlib
        dependencies['matplotlib'] = True
        print(f"✅ Matplotlib {matplotlib.__version__} disponible")
    except ImportError:
        dependencies['matplotlib'] = False
        print("⚠️ Matplotlib no disponible - gráficas deshabilitadas")

    # Keyboard
    try:
        import keyboard
        dependencies['keyboard'] = True
        print("✅ Keyboard disponible - interrupción por teclado habilitada")
    except ImportError:
        dependencies['keyboard'] = False
        print("⚠️ Keyboard no disponible - usar Ctrl+C para interrumpir")

    return dependencies


def load_csv_data(csv_file: str) -> list:
    """Carga datos desde archivo CSV para análisis"""
    import csv

    plot_data = []
    try:
        with open(csv_file, 'r') as f:
            reader = csv.DictReader(f)
            for row in reader:
                plot_data.append({
                    'global_sample': int(row['Global_Sample']),
                    'voltage': float(row['Voltage_V']),
                    'block': int(row['Block'])
                })
    except Exception as e:
        print(f"Error cargando datos CSV: {e}")
        return []

    return plot_data


def main():
    """Función principal del programa"""
    print("🏷️ Sistema de Adquisición de Datos Keithley")
    print("=" * 50)

    # Verificar dependencias
    deps = check_dependencies()
    print()

    # Configurar argumentos
    config_manager = KeithleyConfig()
    args = config_manager.parse_args()

    # Manejar guardado/carga de configuración
    if args.config_save:
        try:
            config_manager.save_config(args.config_save)
            print(f"✅ Configuración guardada en {args.config_save}")
            return
        except Exception as e:
            print(f"❌ Error guardando configuración: {e}")
            return

    if args.config_load:
        try:
            config_manager.load_config(args.config_load)
            print(f"✅ Configuración cargada desde {args.config_load}")
        except Exception as e:
            print(f"❌ Error cargando configuración: {e}")
            return

    # Validar configuración
    valid, error = config_manager.validate_config()
    if not valid:
        print(f"❌ Error de configuración: {error}")
        return

    # Obtener configuración procesada
    config = config_manager.get_processed_config()

    # Configurar logging
    logger = setup_logging(config)

    # Imprimir configuración final
    if not config.get('quiet', False):
        print(f"🏷️ Etiqueta: '{config['experiment_label']}'")
        print(f"📊 Muestras por bloque: {config['samples_per_count']}")
        print(f"⚡ NPLCycles: {config['nplc_cycles']}")
        print(f"🔢 Bloques: {'∞ (indefinido)' if config['infinite_mode'] else config['num_blocks']}")
        print(f"📈 Estadísticas: {'Deshabilitadas' if config['no_stats'] else 'Habilitadas'}")
        print()

    try:
        # Crear instancia de adquisición
        acquirer = KeithleyAcquisition(config, logger)

        # Ejecutar adquisición
        print("🚀 Iniciando adquisición...")
        results = acquirer.run_acquisition()

        if results['error']:
            print(f"❌ Error durante la adquisición: {results['error']}")
            return

        # Verificar que hay datos para analizar
        if results['total_samples'] == 0:
            print("⚠️ No se adquirieron datos")
            return

        # Cargar datos para análisis
        plot_data = load_csv_data(results['csv_file'])
        if not plot_data:
            print("❌ Error cargando datos para análisis")
            return

        # Análisis estadístico
        print("\n📊 Realizando análisis estadístico...")
        analyzer = StatisticalAnalyzer(
            numpy_available=deps['numpy'],
            scipy_available=deps['scipy']
        )

        voltages = [d['voltage'] for d in plot_data]
        stats = analyzer.calculate_comprehensive_stats(voltages)

        # Mostrar estadísticas básicas
        if stats:
            print("📊 Estadísticas principales:")
            print(".6f")
            print(".6f")
            print(".6f")
            print(".6f")
            print(".6f")

            if 'cv' in stats:
                print(".2f")

        # Generar gráficas
        if deps['matplotlib']:
            print("\n📈 Generando gráficas...")
            plotter = KeithleyPlotter(
                output_dir=config['output_dir'],
                experiment_label=config['experiment_label']
            )

            try:
                if config['no_stats']:
                    # Gráfica básica
                    plot_file = plotter.create_basic_plot(plot_data)
                    print(f"✅ Gráfica básica guardada: {plot_file}")
                else:
                    # Gráfica completa con estadísticas
                    block_stats = analyzer.calculate_block_statistics(
                        voltages, config['samples_per_count']
                    ) if deps['numpy'] else None

                    plot_file = plotter.create_comprehensive_plot(
                        plot_data, stats, block_stats
                    )
                    print(f"✅ Gráfica completa guardada: {plot_file}")

            except Exception as e:
                print(f"❌ Error generando gráficas: {e}")
                logger.error(f"Plotting error: {e}")
        else:
            print("⚠️ Matplotlib no disponible - omitiendo gráficas")

        # Resultado final
        print("\n🎉 Proceso completado exitosamente!")
        print(f"📊 Total de muestras: {results['total_samples']}")
        print(f"💾 Datos guardados en: {results['csv_file']}")
        if 'plot_file' in locals():
            print(f"📈 Gráfica guardada en: {plot_file}")

    except KeithleyError as e:
        print(f"❌ Error del sistema Keithley: {e}")
        logger.error(f"Keithley error: {e}")
        return 1
    except KeyboardInterrupt:
        print("\n🛑 Interrupción por usuario")
        logger.warning("Process interrupted by user")
        return 1
    except Exception as e:
        print(f"❌ Error inesperado: {e}")
        logger.error(f"Unexpected error: {e}")
        return 1

    return 0


if __name__ == '__main__':
    sys.exit(main())