#!/usr/bin/env python3
"""
Script de demostración del sistema de carpetas de salida
"""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import KeithleyConfig

def demo_output_folders():
    """Demostración del sistema de carpetas de salida"""

    print("🗂️ Demostración del Sistema de Carpetas de Salida")
    print("=" * 50)

    # Configuración por defecto
    print("\n1. Configuración por defecto:")
    config = KeithleyConfig()
    config.args = config.parser.parse_args(['--label', 'demo'])
    valid, error = config.validate_config()

    print(f"   Directorio por defecto: {config.args.output_dir}")
    print(f"   ¿Válido?: {valid}")
    print(f"   ¿Carpeta existe?: {os.path.exists(config.args.output_dir)}")

    # Configuración personalizada
    print("\n2. Configuración personalizada:")
    config2 = KeithleyConfig()
    config2.args = config2.parser.parse_args([
        '--label', 'demo_custom',
        '--output-dir', 'demo_resultados'
    ])
    valid2, error2 = config2.validate_config()

    print(f"   Directorio personalizado: {config2.args.output_dir}")
    print(f"   ¿Válido?: {valid2}")
    print(f"   ¿Carpeta existe?: {os.path.exists(config2.args.output_dir)}")

    # Mostrar estructura
    print("\n3. Estructura de carpetas:")
    for root, dirs, files in os.walk('.'):
        level = root.replace('.', '').count(os.sep)
        indent = ' ' * 2 * level
        print(f"{indent}{os.path.basename(root)}/")
        subindent = ' ' * 2 * (level + 1)
        for file in files:
            if file.endswith(('.csv', '.png', '.log', '.json')):
                print(f"{subindent}📄 {file}")

    print("\n✅ Demostración completada!")
    print("\n💡 Los archivos CSV y PNG se guardarán automáticamente")
    print("   en la carpeta especificada por --output-dir")

if __name__ == '__main__':
    demo_output_folders()