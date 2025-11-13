# Módulo Main para Adquisición Sincronizada Keithley-Alicat

Este módulo proporciona una interfaz completa y fácil de usar para ejecutar experimentos de adquisición de datos sincronizada entre el multímetro Keithley y el controlador de presión Alicat.

## Características

- ✅ **Configuración completa**: Parámetros para Keithley y Alicat
- ✅ **Validación automática**: Verifica configuraciones antes de iniciar
- ✅ **Pruebas de conexión**: Valida conectividad con instrumentos
- ✅ **Múltiples modos**: Interactivo, línea de comandos, configuración por defecto
- ✅ **Logging completo**: Sistema de logging configurable
- ✅ **Manejo de señales**: Interrupción graceful con Ctrl+C
- ✅ **Threading seguro**: Ejecución en threads separados

## Requisitos

- Python 3.7+
- PyVISA
- PySerial
- NumPy
- Matplotlib
- Pandas
- Instrumentos conectados:
  - Keithley (cualquier modelo compatible con SCPI)
  - Alicat (conectado en COM5)

## Instalación

Asegúrate de tener instaladas las dependencias:

```bash
pip install pyvisa pyserial numpy matplotlib pandas
```

## Uso Básico

### 1. Configuración por Defecto

Ejecuta con todos los parámetros por defecto:

```bash
python main_acquisition.py --default
```

### 2. Configuración Interactiva

Configura el experimento paso a paso:

```bash
python main_acquisition.py --interactive
```

### 3. Configuración por Línea de Comandos

Personaliza parámetros específicos:

```bash
python main_acquisition.py \
    --presion-inicial 0.0 \
    --presion-final 5.0 \
    --ciclos 3 \
    --intervalo 20 \
    --output-dir "mis_datos"
```

## Parámetros de Configuración

### Configuración del Keithley

| Parámetro | Descripción | Valor por Defecto |
|-----------|-------------|-------------------|
| `--output-dir` | Directorio para guardar datos | `lecturas` |
| `--experiment-label` | Etiqueta del experimento | `adquisicion_presion` |
| `--nplc` | Ciclos NPLC (precisión) | `10` |
| `--samples-per-block` | Muestras por bloque | `1000` |
| `--infinite` | Modo adquisición infinita | `False` |
| `--num-blocks` | Número de bloques (modo finito) | `50` |

### Configuración de Presión

| Parámetro | Descripción | Valor por Defecto |
|-----------|-------------|-------------------|
| `--presion-inicial` | Presión inicial (kPa) | `0.0` |
| `--presion-final` | Presión final (kPa) | `6.86` |
| `--intervalo` | Intervalo entre setpoints (s) | `30.0` |
| `--puntos-intermedios` | Puntos intermedios por rampa | `5` |
| `--ciclos` | Número de ciclos completos | `2` |
| `--modo-intermedio` | Modo puntos (`auto`/`manual`) | `auto` |
| `--puntos-personalizados` | Lista de puntos manuales | `[0, 1.5, 3.0, 4.5, 6.86]` |
| `--estabilidad` | Habilitar estabilización | `True` |
| `--tiempo-estabilidad` | Tiempo máximo estabilización (s) | `15.0` |
| `--file-label` | Prefijo para archivos CSV | `ExperimentoPresion` |

### Configuración de Logging

| Parámetro | Descripción | Valor por Defecto |
|-----------|-------------|-------------------|
| `--log-level` | Nivel de logging | `INFO` |
| `--log-file` | Archivo para logs | `None` (solo consola) |

## Ejemplos Avanzados

### Experimento de Alta Precisión

```bash
python main_acquisition.py \
    --nplc 20 \
    --samples-per-block 2000 \
    --presion-final 10.0 \
    --intervalo 60 \
    --log-level DEBUG \
    --log-file experimento.log
```

### Experimento con Puntos Personalizados

```bash
python main_acquisition.py \
    --modo-intermedio manual \
    --puntos-personalizados "[0, 1.0, 2.5, 4.0, 5.5, 7.0]" \
    --ciclos 1 \
    --file-label "PuntosPersonalizados"
```

### Adquisición Infinita

```bash
python main_acquisition.py \
    --infinite \
    --presion-final 8.0 \
    --intervalo 45 \
    --no-estabilidad
```

### Experimento Rápido (Sin Pruebas)

```bash
python main_acquisition.py \
    --default \
    --no-test-connections \
    --log-level WARNING
```

## Modos de Puntos Intermedios

### Modo Automático (`auto`)
Genera automáticamente puntos intermedios entre presión inicial y final.

**Ejemplo**: Inicial=0, Final=6.86, Puntos intermedios=5
- Ciclo subida: [0.0, 1.37, 2.74, 4.11, 5.48, 6.86]
- Ciclo bajada: [6.86, 5.48, 4.11, 2.74, 1.37, 0.0]

### Modo Manual (`manual`)
Usa una lista personalizada de puntos de presión.

**Ejemplo**: `[0, 2, 4, 6.86]`
- Ciclo subida: [0, 2, 4, 6.86]
- Ciclo bajada: [6.86, 4, 2, 0]

## Sistema de Logging

El módulo incluye un sistema completo de logging:

- **DEBUG**: Información detallada para debugging
- **INFO**: Información general del progreso
- **WARNING**: Advertencias no críticas
- **ERROR**: Errores que requieren atención

Los logs se pueden guardar en archivo además de mostrarse en consola:

```bash
python main_acquisition.py --log-file experimento.log --log-level DEBUG
```

## Manejo de Errores

El módulo incluye validación completa de:

- ✅ Conectividad con instrumentos
- ✅ Parámetros de configuración
- ✅ Rangos de valores válidos
- ✅ Permisos de escritura en directorios
- ✅ Interrupciones por teclado (Ctrl+C)

## Archivos de Salida

Los datos se guardan en archivos CSV con el formato:

```
Timestamp,Sample,Ciclo,Fase,KEITHLEY Voltage (V),Alicat Presion (kPA),Alicat Setpoint (kPA),Setpoint Enviado (kPA)
```

**Ejemplo de nombre**: `ExperimentoPresion_20251107_143052.csv`

## Interrupción del Experimento

Para detener un experimento en ejecución:

1. Presiona `Ctrl+C` en la terminal
2. El sistema detendrá graceful la adquisición
3. Se guardarán todos los datos recolectados hasta ese momento
4. Los instrumentos se desconectarán correctamente

## Troubleshooting

### Error de Conexión con Keithley
- Verifica que el instrumento esté encendido
- Confirma que PyVISA esté instalado correctamente
- Revisa que no haya otros programas usando el instrumento

### Error de Conexión con Alicat
- Verifica que esté conectado en COM5
- Confirma la configuración serial (115200 baud)
- Revisa que no haya otros programas usando el puerto

### Errores de Permisos
- Asegúrate de tener permisos de escritura en el directorio de salida
- Verifica que el directorio exista o pueda ser creado

### Errores de Configuración
- Usa `--interactive` para configuración guiada
- Revisa los valores por defecto en este README
- Valida rangos de parámetros antes de ejecutar

## Estructura del Código

```
main_acquisition.py
├── Configuración Global
│   ├── Variables requeridas por acquisition_loop
│   ├── Configuraciones por defecto
│   └── Constantes del sistema
├── Funciones de Configuración
│   ├── setup_logging()
│   ├── validate_configuration()
│   ├── create_output_directory()
│   └── test_instrument_connections()
├── Funciones de Ejecución
│   └── run_acquisition_experiment()
├── Funciones Interactivas
│   └── interactive_configuration()
└── Función Main
    └── main() con argparse
```

## Integración con Código Existente

Este módulo está diseñado para trabajar con `response_single_pulse.py`, importando las funciones necesarias:

- `acquisition_loop()`: Función principal de adquisición
- `detener_adquisicion()`: Función de parada
- `KeithleyAcquisition`: Clase para control del Keithley
- `stability_setpoint()`: Función de estabilización

## Soporte y Desarrollo

Para reportar problemas o solicitar mejoras:

1. Revisa los logs detallados con `--log-level DEBUG`
2. Incluye la configuración completa usada
3. Describe el comportamiento esperado vs observado
4. Incluye información del sistema y versiones de software

---

**Autor**: GuilleDevMX
**Fecha**: Noviembre 2025
**Versión**: 1.0.0