# Sistema de Adquisición Integrada Keithley + Alicat + TIVA

Un sistema completo para adquisición de datos integrada con instrumentos Keithley (multímetro digital), Alicat (controlador de flujo/presión) y TIVA (microcontrolador), incluyendo análisis de histéresis, visualización de datos y exportación profesional.

## 🚀 Características Principales

- **🔬 Adquisición Multi-Instrumento**: Integración simultánea de Keithley (voltaje), Alicat (presión) y TIVA (señales analógicas)
- **📊 Análisis de Histéresis**: Análisis completo de ciclos de histéresis con promedios por fase y exportación organizada
- **🖥️ Interfaz Gráfica Avanzada**: GUI completa con control en tiempo real, visualización y exportación
- **📈 Análisis Estadístico Completo**: Estadísticas descriptivas, correlación, estabilidad y detección de outliers
- **💾 Exportación Profesional**: Múltiples formatos (CSV, Excel) con datos organizados
- **🔧 Configuración Flexible**: Parámetros personalizables y modos automático/manual
- **🛡️ Manejo Robusto de Errores**: Logging detallado y recuperación automática
- **🧪 Scripts Especializados**: Scripts independientes para adquisiciones específicas (TIVA standalone, sin Keithley)
- **🎯 Calibración PID**: Sistema de calibración automática para controlador Alicat

## 📋 Requisitos del Sistema

- **Python**: 3.8 o superior
- **Instrumentos**:
  - Keithley con interfaz USBTMC (compatible con PyVISA)
  - Alicat (conexión serial)
  - TIVA (conexión serial)
- **SO**: Windows, Linux, o macOS
- **Dependencias**: Ver `requirements.txt`

## 📦 Instalación

1. **Clona o descarga** los archivos del proyecto
2. **Instala las dependencias**:
   ```bash
   pip install -r requirements.txt
   ```
3. **Instala NI-VISA** (recomendado para mejor soporte USBTMC):
   - Descarga desde: https://www.ni.com/en/support/downloads/drivers/download.ni-visa.html

## 🏗️ Estructura del Proyecto

El sistema está organizado en archivos principales y carpetas especializadas:

```
KEITHLEY/
├── 📄 main.py                          # 🚀 Interfaz gráfica principal (GUI integrada)
├── 📄 acquisition.py                   # 🔌 Módulo de adquisición Keithley
├── 📄 acquisition_instruments.py       # 🔗 Adquisición integrada Keithley + Alicat + TIVA
├── 📄 acquisition_wo_KEITHLEY.py       # 🔄 Adquisición sin Keithley
├── 📄 tiva_acqusition.py               # 🎯 Adquisición TIVA standalone
├── 📄 alicat_pid_calibration.py        # 🎛️ Calibración PID para Alicat
├── 📄 config.py                        # ⚙️ Configuración para Keithley (línea de comandos)
├── 📄 requirements.txt                 # 📦 Dependencias Python
├── 📄 CodigoPresionADS.c               # 💻 Código C para TIVA (presión ADS)
├── 📁 calibration_data/                # 🎯 Datos de calibración PID
├── 📁 lecturas/                        # 📊 Datos de lecturas y experimentos
├── 📁 logs/                           # 📝 Logs del sistema
├── 📁 solo_keithley/                  # 🔌 Scripts específicos para Keithley
├── 📁 test_kei/                       # 🧪 Tests y ejemplos para Keithley
├── 📁 user_manuals/                   # 📚 Manuales de usuario
├── 📁 kei lecture/                    # 📖 Lecturas y documentación Keithley
└── 📁 __pycache__/                    # 🐍 Archivos compilados Python
```

### 📋 Descripción de Archivos Principales

| Archivo | Descripción | Funcionalidades |
|---------|-------------|-----------------|
| `main.py` | Interfaz gráfica principal | GUI completa con pestañas para control, calibración, visualización y análisis |
| `acquisition.py` | Adquisición Keithley | Clase para control del multímetro digital, análisis estadístico |
| `acquisition_instruments.py` | Adquisición integrada | Sistema completo Keithley + Alicat + TIVA con histéresis |
| `acquisition_wo_KEITHLEY.py` | Adquisición sin Keithley | Alicat + TIVA únicamente |
| `tiva_acqusition.py` | TIVA standalone | Adquisición especializada de 60 segundos con guardado incremental |
| `alicat_pid_calibration.py` | Calibración Alicat | Sistema PID automático para control de presión/flujo |
| `config.py` | Configuración | Argumentos de línea de comandos para Keithley |
| `CodigoPresionADS.c` | Firmware TIVA | Código C para lectura de sensores de presión ADS |

## 🎯 Uso del Sistema

### 🚀 Interfaz Gráfica Principal

```bash
# Ejecutar la interfaz gráfica completa
python main.py
```

**Flujo de trabajo típico:**
1. **Configurar Puertos**: Escanear y probar conexiones seriales (COM5=Alicat, COM6=TIVA)
2. **Ajustar Parámetros**: Configurar setpoints, intervalos, modos de operación
3. **Iniciar Adquisición**: Comenzar captura integrada con monitoreo en tiempo real
4. **Analizar Datos**: Ejecutar análisis de histéresis con promedios por fase
5. **Exportar Resultados**: Guardar datos organizados en CSV/Excel

### 🎯 Adquisición TIVA Independiente

Para adquisición especializada de datos TIVA (60 segundos con guardado incremental):

```bash
# Ejecutar adquisición TIVA standalone
python tiva_acqusition.py
```

**Características:**
- Adquisición de 60 segundos exactos
- Guardado incremental cada 20 muestras
- Cálculo automático de frecuencia de muestreo
- Generación de archivos PWL para simulación
- Cálculo de promedios finales

### 🔧 Adquisición sin Keithley

Para experimentos que no requieren el multímetro Keithley:

```bash
# Ejecutar adquisición Alicat + TIVA únicamente
python acquisition_wo_KEITHLEY.py
```

### 🔌 Adquisición Keithley Básica

Para adquisición simple con Keithley desde línea de comandos:

```bash
# Adquisición básica
python acquisition.py --label "experimento1" --samples 1000 --blocks 10

# Con parámetros personalizados
python acquisition.py --label "voltaje_sensor" --samples 2000 --nplc 0.1 --blocks 5 --force
```

## ⚙️ Configuración del Sistema

### Puertos Seriales
```python
# En los scripts (configuración típica)
alicat_port = "COM5"  # Alicat Flow Controller
tiva_port = "COM6"    # TIVA Microcontroller
```

### Parámetros de Adquisición
```python
# Parámetros de histéresis en acquisition_instruments.py
num_ciclos = 1
punto_inicio = 0
punto_final = 6.867
setpoint_intervalo = 60  # segundos

# Modos de operación
intermediate_mode = "automatic"  # "automatic" o "manual"
stability_time = 15  # segundos de estabilización
```

## 📊 Análisis de Histéresis

El sistema incluye análisis avanzado de histéresis con características únicas:

### ✨ Características del Análisis

- **Ciclos Completos**: Análisis de múltiples ciclos de subida y bajada
- **Promedios por Fase**: Cálculo separado de promedios para fases de subida y bajada
- **Área de Histéresis**: Cálculo del área usando integración trapezoidal
- **Detección Automática**: Identificación automática de transiciones de ciclo
- **Exportación Organizada**: Datos separados en secciones claras

### 📈 Resultados del Análisis

**Métricas calculadas:**
- Área de histéresis por ciclo (TIVA raw, filtrado, Keithley)
- Promedios por setpoint en cada fase
- Error de histéresis (diferencia subida-bajada)
- Estadísticas globales del experimento

**Formatos de exportación:**
- **CSV**: Secciones separadas para promedios y datos de histéresis
- **Excel**: Múltiples hojas (Promedios_por_Fase, Datos_Histeresis)

## 🖥️ Interfaz Gráfica Detallada

### 📑 Pestañas Principales

1. **🎛️ Control**: Parámetros de adquisición, botones de inicio/parada/pausa
2. **🔧 Calibración**: Control PID del Alicat con ganancias ajustables
3. **📊 Visualización**: Carga y análisis de archivos CSV existentes
4. **📈 Análisis**: Análisis de histéresis con exportación profesional
5. **💾 Exportación**: Configuración de formatos de exportación
6. **🔌 Puertos**: Escaneo y prueba de conexiones de instrumentos

### 🎨 Funcionalidades de Visualización

- **Series Temporales**: Voltajes TIVA (raw/filtrado), Keithley, presión Alicat
- **Análisis de Correlación**: Matrices de correlación entre variables
- **Histogramas**: Distribuciones de todas las variables medidas
- **Análisis Espectral**: FFT de señales para análisis de frecuencia
- **Tendencias**: Análisis de tendencias temporales
- **Estadísticas**: Resúmenes estadísticos completos

## 📁 Estructura de Datos

### Archivos CSV de Adquisición
```csv
Timestamp,Sample,Ciclo,Fase,TIVA Voltage (V),TIVA Voltage w/FPB(V),KEITHLEY Voltage (V),TIVA Temp (C),Alicat Presion (kPA),Alicat Setpoint (kPA),Setpoint Enviado (kPA)
2025-10-29 14:30:15.123,1,1,subida,2.345,2.341,2.340,25.6,1.234,1.200,1.200
...
```

### Archivos de Análisis de Histéresis

**CSV Exportado:**
```csv
=== PROMEDIOS POR FASE ===
Ciclo,Fase,Setpoint_kPA,TIVA_Voltage_V,TIVA_Voltage_FP_V,KEITHLEY_Voltage_V
1,Subida,1.2,2.345,2.341,2.340
1,Bajada,1.2,2.348,2.344,2.343

=== DATOS DE HISTERESIS ===
Ciclo,Setpoint_kPA,Error_TIVA_V,Error_TIVA_FP_V,Error_Keithley_V,Area_TIVA,Area_TIVA_FP,Area_Keithley
1,1.2,-0.003,-0.003,-0.003,0.045,0.042,0.041
```

**Excel (Múltiples Hojas):**
- `Promedios_por_Fase`: Promedios separados por ciclo y fase
- `Datos_Histeresis`: Datos de error y áreas calculadas

## 🔧 Desarrollo y Extensión

### Agregar Nuevo Análisis

1. **Crear función en `acquisition_instruments.py`** o módulo separado:
```python
def run_mi_analisis(data: pd.DataFrame, **params) -> Dict[str, Any]:
    # Implementar lógica de análisis
    results = {"mi_metrica": calcular_metrica(data)}
    return results
```

2. **Agregar a GUI en `main.py`**:
```python
def run_mi_analisis(self):
    results = run_mi_analisis(self.csv_data)
    self.display_analysis_figure(results['figure'], 'mi_analisis')
```

### Agregar Nuevo Instrumento

1. **Crear clase similar a `AlicatController`**:
```python
class MiInstrumento:
    def __init__(self, config):
        # Inicialización

    def read_data(self):
        # Lectura de datos
        return data
```

2. **Integrar en `acquisition_instruments.py`**:
```python
# Agregar llamadas de lectura en acquisition_loop
mi_instrumento = MiInstrumento(config)
data = mi_instrumento.read_data()
```

## 🧪 Tests y Validación

Ejecutar tests del sistema:
```bash
# Tests unitarios
python -m pytest test_kei/ -v

# Tests de integración
python test_kei/test_main_acquisition.py
```

## 🚨 Solución de Problemas

### Problema: "ModuleNotFoundError: No module named 'pandas'"
**Solución**: Instalar dependencias
```bash
pip install -r requirements.txt
```

### Problema: Puertos seriales no encontrados
**Solución**:
1. Verificar conexiones físicas
2. Usar "Escanear Puertos" en la GUI
3. Verificar configuración en los scripts

### Problema: Error de estabilidad en adquisición
**Solución**:
- Aumentar `stability_time` en configuración
- Verificar conexiones de instrumentos
- Revisar logs en carpeta `logs/`

### Problema: Análisis de histéresis falla
**Solución**:
- Verificar que el CSV contenga columnas requeridas
- Asegurar que existan múltiples ciclos
- Revisar formato de datos (números, no texto)

### Problema: GUI no responde durante adquisición
**Solución**: La GUI usa threading, esperar a que termine la operación actual

## 📝 Registro de Cambios

### v3.0 (Actual) - Sistema Integrado Completo
- ✅ **GUI Completa**: Interfaz gráfica integrada en `main.py`
- ✅ **Análisis de histéresis avanzado**: Promedios por fase y exportación organizada
- ✅ **Módulos especializados**: Scripts separados para diferentes configuraciones
- ✅ **Calibración PID**: Sistema automático para Alicat
- ✅ **Documentación completa**: README actualizado y estructurado

### v2.0 - Sistema Integrado Básico
- 🔄 Integración Keithley + Alicat + TIVA
- 🔄 Análisis básico de histéresis
- 🔄 Scripts separados por funcionalidad

### v1.0 - Sistema Keithley Básico
- 📊 Adquisición Keithley con análisis estadístico
- 📈 Visualización básica
- ⚙️ Configuración por línea de comandos

## 🤝 Contribución

Para contribuir al proyecto:

1. **Fork** el repositorio
2. **Crear rama** para nueva funcionalidad: `git checkout -b feature/nueva-funcionalidad`
3. **Implementar** cambios siguiendo la estructura existente
4. **Agregar tests** para nueva funcionalidad
5. **Documentar** cambios en el README
6. **Crear Pull Request** con descripción detallada

## 📄 Licencia

Este proyecto es software libre distribuido bajo la licencia MIT. Consulta el archivo LICENSE para detalles completos.

---

**Desarrollado por**: GuilleDevMX
**Última actualización**: Diciembre 2025
**Versión**: 3.0.0

### Gestión de Configuración

**Guardar configuración**:
```bash
python main_refactored.py --config-save mi_config.json --label "test" --samples 1000
```

**Cargar configuración**:
```bash
python main_refactored.py --config-load mi_config.json
```

## 📊 Análisis Estadístico

El sistema calcula automáticamente estadísticas avanzadas incluyendo:

### Estadísticas Básicas
- Media, desviación estándar, varianza
- Mínimo, máximo, rango
- Desviación media absoluta (MAD)
- Coeficiente de variación

### Estadísticas Avanzadas (con NumPy/SciPy)
- Asimetría (skewness) y curtosis
- Autocorrelación (lag 1 y completa)
- Correlación temporal
- Percentiles (Q25, Q75, IQR)
- Análisis de estabilidad

### Detección de Outliers
- Método IQR (interquartile range)
- Método Z-score
- Método Modified Z-score

## 📈 Visualización

### Gráfica Completa (por defecto)
- **Serie temporal**: Datos con líneas de referencia (media ± σ)
- **Distribución**: Histograma con KDE (si SciPy disponible)
- **Estadísticas por bloque**: Media y desviación por bloque
- **Autocorrelación**: Función de autocorrelación
- **Análisis de estabilidad**: Estadísticas móviles
- **Resumen estadístico**: Tabla completa de métricas

### Gráfica Básica (`--no-stats`)
- Serie temporal simple
- Histograma básico

## 🧪 Tests

Ejecutar todos los tests:
```bash
python -m pytest test_main.py -v
```

Ejecutar con cobertura:
```bash
python -m pytest test_main.py --cov=. --cov-report=html
```

## 🔧 Desarrollo y Mantenimiento

### Agregar Nueva Funcionalidad

1. **Para análisis estadístico**: Extender `StatisticalAnalyzer` en `analysis.py`
2. **Para visualización**: Agregar métodos a `KeithleyPlotter` en `plotting.py`
3. **Para configuración**: Modificar `KeithleyConfig` en `config.py`
4. **Para adquisición**: Extender `KeithleyAcquisition` en `acquisition.py`

### Manejo de Errores

El sistema incluye excepciones personalizadas:
- `KeithleyError`: Base para todos los errores del sistema
- `KeithleyConnectionError`: Problemas de conexión
- `KeithleyAcquisitionError`: Errores durante adquisición

### Logging

Logs se guardan automáticamente en:
- `keithley_acquisition_YYYYMMDD.log`
- Nivel INFO por defecto
- Incluye timestamps y niveles de severidad

## 🚨 Solución de Problemas

### Problema: "No se encontraron instrumentos conectados"
**Solución**:
1. Verificar conexión USB del Keithley
2. Instalar NI-VISA
3. Verificar configuración del instrumento

### Problema: "NumPy no disponible"
**Solución**:
```bash
pip install numpy
```
Algunas estadísticas estarán limitadas pero el sistema funcionará.

### Problema: "Error de timeout"
**Solución**:
- Reducir `--samples` por bloque
- Aumentar `--nplc` (menos precisión pero más rápido)
- Verificar configuración del instrumento

### Problema: Gráficas no se generan
**Solución**:
```bash
pip install matplotlib
```

## 📝 Notas de Versión

### v2.0 (Actual)
- **Modularización completa**: Código dividido en módulos independientes
- **Sistema de configuración**: Archivos JSON para configuración
- **Tests unitarios**: Cobertura completa con pytest
- **Manejo de errores mejorado**: Excepciones personalizadas
- **Documentación completa**: README y docstrings

### v1.0 (Legacy)
- Sistema monolítico en `main.py`
- Funcionalidad básica completa
- Sin tests automatizados

## 🤝 Contribución

Para contribuir:
1. Crear rama feature desde `main`
2. Agregar tests para nueva funcionalidad
3. Ejecutar todos los tests
4. Crear pull request con descripción detallada

## 📄 Licencia

Este proyecto es software libre. Consulta el archivo LICENSE para detalles.