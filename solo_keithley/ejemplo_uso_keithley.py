#!/usr/bin/env python3
"""
Ejemplo de uso del módulo solo_keithley.py

Este script muestra cómo usar la clase KeithleyAcquisition para adquirir datos
del multímetro digital Keithley.
"""

import logging
import sys
import os

# Agregar el directorio actual al path para importar solo_keithley
sys.path.append(os.path.dirname(__file__))

from solo_keithley import KeithleyAcquisition

def main():
    """Función principal con ejemplo de uso"""

    # === CONFIGURACIÓN DEL EXPERIMENTO ===
    config = {
        'output_dir': 'lecturas',                    # Directorio para guardar datos
        'experiment_label': 'ejemplo_basico',       # Etiqueta del experimento
        'nplc_cycles': 1,                           # Ciclos NPLC (precisión: 0.001 = alta, 10 = baja)
        'samples_per_count': 1,                    # Muestras por bloque
        'num_blocks': 5,                            # Número de bloques a adquirir
        'infinite_mode': True,                     # False = modo finito, True = infinito
        'quiet': False                              # False = mostrar prompts, True = silencioso
    }

    # === CONFIGURACIÓN DE LOGGING ===
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler('keithley_acquisition.log')
        ]
    )

    logger = logging.getLogger(__name__)

    print("=" * 60)
    print("EJEMPLO DE USO - ADQUISICIÓN KEITHLEY")
    print("=" * 60)
    print(f"Directorio de salida: {config['output_dir']}")
    print(f"Etiqueta: {config['experiment_label']}")
    print(f"NPLC: {config['nplc_cycles']}")
    print(f"Muestras por bloque: {config['samples_per_count']}")
    print(f"Número de bloques: {config['num_blocks']}")
    print("=" * 60)

    try:
        # === CREAR INSTANCIA DEL ADQUISIDOR ===
        logger.info("Creando instancia del adquisidor Keithley...")
        keithley = KeithleyAcquisition(config, logger)

        # === EJECUTAR ADQUISICIÓN ===
        logger.info("Iniciando adquisición...")
        results = keithley.run_acquisition()

        # === MOSTRAR RESULTADOS ===
        print("\n" + "=" * 60)
        print("RESULTADOS DE LA ADQUISICIÓN")
        print("=" * 60)

        if results['error']:
            print(f"❌ Error: {results['error']}")
            return 1

        print("✅ Adquisición completada exitosamente!")
        print(f"📊 Total de muestras: {results['total_samples']}")
        print(f"📦 Bloques completados: {results['blocks_completed']}")
        print(f"⏱️ Tiempo total: {results['total_time']:.3f} segundos")
        print(f"💾 Archivo CSV: {results['csv_file']}")

        if results['interrupted']:
            print("⚠️ La adquisición fue interrumpida por el usuario")

        return 0

    except Exception as e:
        logger.error(f"Error fatal durante la adquisición: {e}")
        print(f"\n❌ Error fatal: {e}")
        return 1

def ejemplo_configuraciones():
    """Ejemplos de diferentes configuraciones"""

    print("\n" + "=" * 60)
    print("EJEMPLOS DE CONFIGURACIONES")
    print("=" * 60)

    # Configuración de alta precisión
    config_alta_precision = {
        'output_dir': 'lecturas',
        'experiment_label': 'alta_precision',
        'nplc_cycles': 10,          # Alta precisión (más lento)
        'samples_per_count': 1,     # Una muestra por bloque
        'num_blocks': 100,          # Muchos bloques
        'infinite_mode': False,
        'quiet': True
    }

    # Configuración de alta velocidad
    config_alta_velocidad = {
        'output_dir': 'lecturas',
        'experiment_label': 'alta_velocidad',
        'nplc_cycles': 0.1,         # Baja precisión (más rápido)
        'samples_per_count': 100,   # Muchas muestras por bloque
        'num_blocks': 10,           # Pocos bloques
        'infinite_mode': False,
        'quiet': True
    }

    # Configuración infinita (hasta interrupción manual)
    config_infinita = {
        'output_dir': 'lecturas',
        'experiment_label': 'adquisicion_continua',
        'nplc_cycles': 1,
        'samples_per_count': 10,
        'num_blocks': 1,            # No importa en modo infinito
        'infinite_mode': True,      # Modo infinito
        'quiet': False
    }

    print("1. Alta Precisión:")
    print(f"   NPLC: {config_alta_precision['nplc_cycles']} (lento pero preciso)")
    print(f"   Muestras: {config_alta_precision['samples_per_count']} x {config_alta_precision['num_blocks']} bloques")

    print("\n2. Alta Velocidad:")
    print(f"   NPLC: {config_alta_velocidad['nplc_cycles']} (rápido pero menos preciso)")
    print(f"   Muestras: {config_alta_velocidad['samples_per_count']} x {config_alta_velocidad['num_blocks']} bloques")

    print("\n3. Adquisición Infinita:")
    print("   Modo continuo hasta interrupción manual (presiona 'q' o 'ESC')")
    print(f"   NPLC: {config_infinita['nplc_cycles']}")

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--examples":
        # Mostrar ejemplos de configuraciones
        ejemplo_configuraciones()
    else:
        # Ejecutar adquisición
        exit_code = main()
        sys.exit(exit_code)