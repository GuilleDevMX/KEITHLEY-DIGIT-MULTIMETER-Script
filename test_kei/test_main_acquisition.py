#!/usr/bin/env python3
"""
Script de prueba rápida para el módulo main_acquisition

Este script verifica que todas las importaciones funcionen correctamente
y que la configuración básica sea válida, sin ejecutar un experimento completo.
"""

import sys
import os
from pathlib import Path

def test_imports():
    """Prueba que todas las importaciones funcionen"""
    print("🔍 Probando importaciones...")

    try:
        # Agregar el directorio actual al path
        current_dir = Path(__file__).parent
        sys.path.insert(0, str(current_dir))

        # Importar funciones principales
        from main_acquisition import (
            setup_logging,
            run_acquisition_experiment,
            validate_configuration,
            DEFAULT_KEITHLEY_CONFIG,
            DEFAULT_ACQUISITION_PARAMS
        )
        print("✅ Importaciones de main_acquisition exitosas")

        # Importar del módulo response_single_pulse
        from response_single_pulse import (
            acquisition_loop,
            KeithleyAcquisition,
            stability_setpoint
        )
        print("✅ Importaciones de response_single_pulse exitosas")

        return True

    except ImportError as e:
        print(f"❌ Error de importación: {e}")
        return False
    except Exception as e:
        print(f"❌ Error inesperado: {e}")
        return False

def test_configuration():
    """Prueba que la configuración por defecto sea válida"""
    print("🔧 Probando configuración por defecto...")

    try:
        from main_acquisition import (
            validate_configuration,
            DEFAULT_KEITHLEY_CONFIG,
            DEFAULT_ACQUISITION_PARAMS
        )

        # Validar configuración
        is_valid = validate_configuration(DEFAULT_KEITHLEY_CONFIG, DEFAULT_ACQUISITION_PARAMS)

        if is_valid:
            print("✅ Configuración por defecto válida")
            return True
        else:
            print("❌ Configuración por defecto inválida")
            return False

    except Exception as e:
        print(f"❌ Error probando configuración: {e}")
        return False

def test_dependencies():
    """Prueba que las dependencias externas estén disponibles"""
    print("📦 Probando dependencias externas...")

    dependencies = [
        ('pyvisa', 'PyVISA'),
        ('serial', 'PySerial'),
        ('numpy', 'NumPy'),
        ('matplotlib', 'Matplotlib'),
        ('pandas', 'Pandas'),
        ('logging', 'Logging (estándar)'),
        ('threading', 'Threading (estándar)'),
        ('csv', 'CSV (estándar)'),
        ('datetime', 'Datetime (estándar)'),
        ('pathlib', 'Pathlib (estándar)'),
        ('argparse', 'Argparse (estándar)')
    ]

    missing_deps = []

    for module_name, display_name in dependencies:
        try:
            if module_name == 'serial':
                import serial
            elif module_name == 'pyvisa':
                import pyvisa
            elif module_name == 'numpy':
                import numpy
            elif module_name == 'matplotlib':
                import matplotlib
            elif module_name == 'pandas':
                import pandas
            else:
                __import__(module_name)
            print(f"✅ {display_name} disponible")
        except ImportError:
            print(f"❌ {display_name} no disponible")
            missing_deps.append(display_name)

    if missing_deps:
        print(f"\n⚠️  Dependencias faltantes: {', '.join(missing_deps)}")
        print("Instala con: pip install " + " ".join([d.lower().replace(' ', '-') for d in missing_deps]))
        return False
    else:
        print("✅ Todas las dependencias disponibles")
        return True

def test_file_structure():
    """Prueba que la estructura de archivos sea correcta"""
    print("📁 Probando estructura de archivos...")

    required_files = [
        'main_acquisition.py',
        'response_single_pulse.py',
        'config_ejemplo.py'
    ]

    current_dir = Path(__file__).parent
    missing_files = []

    for filename in required_files:
        if (current_dir / filename).exists():
            print(f"✅ {filename} encontrado")
        else:
            print(f"❌ {filename} no encontrado")
            missing_files.append(filename)

    if missing_files:
        print(f"\n⚠️  Archivos faltantes: {', '.join(missing_files)}")
        return False
    else:
        print("✅ Estructura de archivos completa")
        return True

def test_config_file():
    """Prueba que el archivo de configuración se pueda cargar"""
    print("⚙️  Probando archivo de configuración...")

    try:
        # Importar configuración
        from config_ejemplo import (
            KEITHLEY_CONFIG,
            ACQUISITION_PARAMS,
            EXECUTION_CONFIG,
            load_config,
            validate_config
        )
        print("✅ Archivo de configuración importado")

        # Probar función de validación
        errors = validate_config(KEITHLEY_CONFIG, ACQUISITION_PARAMS)
        if errors:
            print(f"❌ Errores en configuración: {errors}")
            return False
        else:
            print("✅ Configuración del archivo válida")

        # Probar carga de configuraciones predefinidas
        for config_name in ['rapido', 'precision', 'monitoreo', 'histeresis']:
            try:
                k, a, e = load_config(config_name)
                print(f"✅ Configuración '{config_name}' cargada")
            except Exception as e:
                print(f"❌ Error cargando '{config_name}': {e}")
                return False

        return True

    except Exception as e:
        print(f"❌ Error probando configuración: {e}")
        return False

def test_logging():
    """Prueba que el sistema de logging funcione"""
    print("📝 Probando sistema de logging...")

    try:
        from main_acquisition import setup_logging
        import logging

        # Configurar logging temporal
        logger = setup_logging(level=logging.INFO)
        logger.info("Mensaje de prueba del sistema de logging")
        print("✅ Sistema de logging funcional")

        return True

    except Exception as e:
        print(f"❌ Error en sistema de logging: {e}")
        return False

def run_all_tests():
    """Ejecuta todas las pruebas"""
    print("=" * 60)
    print("TESTS DE VERIFICACIÓN - main_acquisition")
    print("=" * 60)

    tests = [
        ("Importaciones", test_imports),
        ("Dependencias", test_dependencies),
        ("Estructura de archivos", test_file_structure),
        ("Configuración", test_configuration),
        ("Archivo de configuración", test_config_file),
        ("Sistema de logging", test_logging)
    ]

    results = []
    for test_name, test_func in tests:
        print(f"\n--- {test_name} ---")
        try:
            result = test_func()
            results.append((test_name, result))
        except Exception as e:
            print(f"❌ Error ejecutando {test_name}: {e}")
            results.append((test_name, False))

    # Resumen
    print("\n" + "=" * 60)
    print("RESUMEN DE TESTS")
    print("=" * 60)

    passed = 0
    total = len(results)

    for test_name, result in results:
        status = "✅ PASÓ" if result else "❌ FALLÓ"
        print(f"{status} - {test_name}")
        if result:
            passed += 1

    print(f"\n📊 Resultado: {passed}/{total} tests pasaron")

    if passed == total:
        print("🎉 ¡Todos los tests pasaron! El sistema está listo para usar.")
        print("\nPara ejecutar un experimento:")
        print("  python main_acquisition.py --default")
        print("  python main_acquisition.py --interactive")
        return True
    else:
        print("⚠️  Algunos tests fallaron. Revisa los errores arriba.")
        return False

def main():
    """Función principal"""
    if len(sys.argv) > 1 and sys.argv[1] == "--quick":
        # Modo rápido: solo pruebas críticas
        print("🚀 Modo rápido: probando solo componentes críticos...")
        critical_tests = [test_imports, test_dependencies, test_configuration]

        all_passed = True
        for test_func in critical_tests:
            try:
                if not test_func():
                    all_passed = False
            except:
                all_passed = False

        if all_passed:
            print("✅ Tests críticos pasaron - sistema funcional")
        else:
            print("❌ Tests críticos fallaron")
        return
    else:
        # Tests completos
        success = run_all_tests()
        sys.exit(0 if success else 1)

if __name__ == "__main__":
    main()