#!/usr/bin/env python3
"""
Ejemplo de uso programático del módulo main_acquisition

Este script muestra cómo usar las funciones del módulo main_acquisition
desde código Python, en lugar de línea de comandos.
"""

import sys
import os
from pathlib import Path

# Agregar el directorio actual al path
current_dir = Path(__file__).parent
sys.path.insert(0, str(current_dir))

# Importar funciones del módulo main_acquisition
from main_acquisition import (
    setup_logging,
    run_acquisition_experiment,
    DEFAULT_KEITHLEY_CONFIG,
    DEFAULT_ACQUISITION_PARAMS
)

def ejemplo_basico():
    """
    Ejemplo básico con configuración por defecto
    """
    print("🚀 Ejecutando ejemplo básico...")

    # Configurar logging
    setup_logging(level=20)  # INFO level

    # Ejecutar con configuración por defecto
    success = run_acquisition_experiment()

    print(f"✅ Resultado: {'Éxito' if success else 'Error'}")

def ejemplo_personalizado():
    """
    Ejemplo con configuración personalizada
    """
    print("🔧 Ejecutando ejemplo personalizado...")

    # Configurar logging con archivo
    setup_logging(
        level=20,  # INFO level
        log_file="ejemplo_personalizado.log"
    )

    # Configuración personalizada del Keithley
    keithley_config = DEFAULT_KEITHLEY_CONFIG.copy()
    keithley_config.update({
        'output_dir': 'datos_ejemplo',
        'experiment_label': 'ejemplo_personalizado',
        'nplc_cycles': 5,  # Menos precisión para ejemplo rápido
        'samples_per_count': 500,  # Menos muestras
        'infinite_mode': False,
        'num_blocks': 10
    })

    # Configuración personalizada de adquisición
    acquisition_params = DEFAULT_ACQUISITION_PARAMS.copy()
    acquisition_params.update({
        'setpoint_inicial': 0.0,
        'setpoint_final': 3.0,  # Presión más baja para ejemplo
        'setpoint_intervalo': 15.0,  # Menos tiempo entre cambios
        'num_puntos_intermedios': 3,
        'num_ciclos': 1,  # Solo un ciclo
        'enable_stability': True,
        'stability_time': 10.0,
        'file_label': 'EjemploPersonalizado'
    })

    # Ejecutar experimento
    success = run_acquisition_experiment(
        keithley_config=keithley_config,
        acquisition_params=acquisition_params,
        test_connections=True
    )

    print(f"✅ Resultado: {'Éxito' if success else 'Error'}")

def ejemplo_puntos_manuales():
    """
    Ejemplo con puntos de presión personalizados
    """
    print("📝 Ejecutando ejemplo con puntos manuales...")

    # Configurar logging
    setup_logging(level=20)

    # Configuración con puntos manuales
    acquisition_params = DEFAULT_ACQUISITION_PARAMS.copy()
    acquisition_params.update({
        'intermediate_mode': 'manual',
        'custom_points_text': '[0, 1.0, 2.5, 4.0, 5.5]',  # Puntos personalizados
        'num_ciclos': 1,
        'setpoint_intervalo': 20.0,
        'file_label': 'PuntosManuales'
    })

    # Ejecutar
    success = run_acquisition_experiment(
        acquisition_params=acquisition_params
    )

    print(f"✅ Resultado: {'Éxito' if success else 'Error'}")

def ejemplo_sin_pruebas():
    """
    Ejemplo sin pruebas de conexión (más rápido)
    """
    print("⚡ Ejecutando ejemplo sin pruebas de conexión...")

    # Configurar logging mínimo
    setup_logging(level=30)  # WARNING level

    # Configuración rápida
    keithley_config = DEFAULT_KEITHLEY_CONFIG.copy()
    keithley_config.update({
        'samples_per_count': 100,  # Muy pocas muestras para ejemplo
        'infinite_mode': False,
        'num_blocks': 2
    })

    acquisition_params = DEFAULT_ACQUISITION_PARAMS.copy()
    acquisition_params.update({
        'num_ciclos': 1,
        'setpoint_intervalo': 5.0,  # Muy rápido
        'enable_stability': False,  # Sin estabilización
        'file_label': 'EjemploRapido'
    })

    # Ejecutar sin pruebas de conexión
    success = run_acquisition_experiment(
        keithley_config=keithley_config,
        acquisition_params=acquisition_params,
        test_connections=False
    )

    print(f"✅ Resultado: {'Éxito' if success else 'Error'}")

def main():
    """
    Función principal con menú de ejemplos
    """
    print("=" * 60)
    print("EJEMPLOS DE USO PROGRAMÁTICO - main_acquisition")
    print("=" * 60)

    ejemplos = {
        '1': ('Básico (configuración por defecto)', ejemplo_basico),
        '2': ('Personalizado (configuración completa)', ejemplo_personalizado),
        '3': ('Puntos manuales', ejemplo_puntos_manuales),
        '4': ('Sin pruebas de conexión (rápido)', ejemplo_sin_pruebas),
        '5': ('Ejecutar todos los ejemplos', None)
    }

    while True:
        print("\nEjemplos disponibles:")
        for key, (desc, _) in ejemplos.items():
            print(f"  {key}. {desc}")

        print("  0. Salir")

        choice = input("\nSelecciona un ejemplo (0-5): ").strip()

        if choice == '0':
            print("👋 ¡Hasta luego!")
            break
        elif choice == '5':
            print("\n🚀 Ejecutando todos los ejemplos...")
            for key, (desc, func) in ejemplos.items():
                if key != '5' and func:
                    print(f"\n--- {desc} ---")
                    try:
                        func()
                    except Exception as e:
                        print(f"❌ Error en {desc}: {e}")
                    print()
        elif choice in ejemplos and ejemplos[choice][1]:
            desc, func = ejemplos[choice]
            print(f"\n--- {desc} ---")
            try:
                func()
            except KeyboardInterrupt:
                print("\n⏹️  Ejemplo interrumpido por usuario")
            except Exception as e:
                print(f"❌ Error: {e}")
            print()
        else:
            print("❌ Opción inválida")

        input("Presiona Enter para continuar...")

if __name__ == "__main__":
    main()