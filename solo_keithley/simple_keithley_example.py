#!/usr/bin/env python3
"""
Ejemplo simple de uso del módulo solo_keithley.py
"""

import sys
import os
sys.path.append(os.path.dirname(__file__))

from solo_keithley import KeithleyAcquisition

def main():
    # Configuración básica
    config = {
        'output_dir': 'lecturas',
        'experiment_label': 'prueba_simple',
        'nplc_cycles': 1,          # Precisión estándar
        'samples_per_count': 1000,    # 1000 muestras por bloque
        'num_blocks': 2,           # 2 bloques
        'infinite_mode': False,    # Modo finito
        'quiet': True              # Sin prompts
    }

    print("Iniciando adquisición Keithley...")
    print(f"Configuración: {config['samples_per_count']} muestras x {config['num_blocks']} bloques")

    # Crear adquisidor
    keithley = KeithleyAcquisition(config)

    # Ejecutar adquisición
    results = keithley.run_acquisition()

    # Mostrar resultados
    if results['error']:
        print(f"❌ Error: {results['error']}")
        return 1
    else:
        print("✅ Adquisición exitosa!")
        print(f"📊 Muestras totales: {results['total_samples']}")
        print(f"💾 Archivo: {results['csv_file']}")
        return 0

if __name__ == "__main__":
    sys.exit(main())