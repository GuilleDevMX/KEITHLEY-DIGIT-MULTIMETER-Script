"""
Módulo de análisis estadístico para datos de voltaje Keithley
"""
from typing import Dict, List, Optional, Any
import numpy as np
from scipy import stats as scipy_stats


class StatisticalAnalyzer:
    """Clase para análisis estadístico avanzado de datos de voltaje"""

    def __init__(self, numpy_available: bool = True, scipy_available: bool = True):
        self.numpy_available = numpy_available
        self.scipy_available = scipy_available

    def calculate_comprehensive_stats(self, voltages: List[float]) -> Dict[str, Any]:
        """
        Calcula estadísticas avanzadas de los datos de voltaje

        Args:
            voltages: Lista de valores de voltaje

        Returns:
            Diccionario con todas las estadísticas calculadas
        """
        if not voltages:
            return {}

        stats = {}

        if self.numpy_available:
            voltages_array = np.array(voltages)
            stats.update(self._calculate_numpy_stats(voltages_array))
        else:
            stats.update(self._calculate_basic_stats(voltages))

        return stats

    def _calculate_numpy_stats(self, voltages_array: np.ndarray) -> Dict[str, Any]:
        """Calcula estadísticas usando NumPy y SciPy"""
        stats = {}

        # Estadísticas básicas con numpy
        stats['mean'] = float(np.mean(voltages_array))
        stats['std'] = float(np.std(voltages_array, ddof=1))  # ddof=1 para muestra
        stats['variance'] = float(np.var(voltages_array, ddof=1))
        stats['min'] = float(np.min(voltages_array))
        stats['max'] = float(np.max(voltages_array))
        stats['range'] = float(stats['max'] - stats['min'])

        # Desviación media absoluta (MAD)
        stats['mad'] = float(np.mean(np.abs(voltages_array - stats['mean'])))

        # Coeficiente de variación
        stats['cv'] = (stats['std'] / stats['mean']) * 100 if stats['mean'] != 0 else 0

        # Percentiles
        stats['median'] = float(np.median(voltages_array))
        stats['q25'] = float(np.percentile(voltages_array, 25))
        stats['q75'] = float(np.percentile(voltages_array, 75))
        stats['iqr'] = float(stats['q75'] - stats['q25'])

        # Asimetría (skewness)
        if self.scipy_available:
            stats['skewness'] = float(scipy_stats.skew(voltages_array))
            stats['kurtosis'] = float(scipy_stats.kurtosis(voltages_array))
        else:
            # Cálculo manual aproximado
            if stats['std'] != 0:
                stats['skewness'] = float(np.mean(((voltages_array - stats['mean']) / stats['std']) ** 3))
                stats['kurtosis'] = float(np.mean(((voltages_array - stats['mean']) / stats['std']) ** 4) - 3)

        # Autocorrelación
        if len(voltages_array) > 1:
            stats['autocorr_lag1'] = float(np.corrcoef(voltages_array[:-1], voltages_array[1:])[0, 1])

            # Autocorrelación para múltiples lags (hasta 10)
            max_lag = min(10, len(voltages_array) // 4)
            autocorr_values = []
            for lag in range(1, max_lag + 1):
                corr = np.corrcoef(voltages_array[:-lag], voltages_array[lag:])[0, 1]
                autocorr_values.append(float(corr))
            stats['autocorr_full'] = autocorr_values

        # Correlación con el índice de tiempo (tendencia)
        time_indices = np.arange(len(voltages_array))
        if len(time_indices) > 1:
            stats['time_correlation'] = float(np.corrcoef(time_indices, voltages_array)[0, 1])

        # Estadísticas de estabilidad (últimas vs primeras muestras)
        if len(voltages_array) > 100:
            split_point = len(voltages_array) // 2
            first_half = voltages_array[:split_point]
            second_half = voltages_array[split_point:]

            stats['stability_mean_diff'] = float(np.mean(second_half) - np.mean(first_half))
            stats['stability_std_ratio'] = float(np.std(second_half) / np.std(first_half)) if np.std(first_half) != 0 else 0

        return stats

    def _calculate_basic_stats(self, voltages: List[float]) -> Dict[str, Any]:
        """Calcula estadísticas básicas sin NumPy"""
        n = len(voltages)
        mean = sum(voltages) / n

        # Varianza y desviación estándar
        variance = sum((x - mean) ** 2 for x in voltages) / (n - 1) if n > 1 else 0
        std = variance ** 0.5

        # MAD
        mad = sum(abs(x - mean) for x in voltages) / n

        # Percentiles básicos (aproximados)
        sorted_voltages = sorted(voltages)
        median = sorted_voltages[n // 2]
        q25 = sorted_voltages[n // 4]
        q75 = sorted_voltages[3 * n // 4]
        iqr = q75 - q25

        return {
            'mean': mean,
            'std': std,
            'variance': variance,
            'mad': mad,
            'min': min(voltages),
            'max': max(voltages),
            'range': max(voltages) - min(voltages),
            'median': median,
            'q25': q25,
            'q75': q75,
            'iqr': iqr
        }

    def detect_outliers(self, voltages: List[float], method: str = 'iqr',
                       threshold: float = 1.5) -> Dict[str, Any]:
        """
        Detecta valores atípicos en los datos

        Args:
            voltages: Lista de valores de voltaje
            method: Método de detección ('iqr', 'zscore', 'modified_zscore')
            threshold: Umbral para detección

        Returns:
            Diccionario con información sobre outliers
        """
        if not voltages or not self.numpy_available:
            return {'outliers': [], 'outlier_indices': [], 'outlier_percentage': 0}

        voltages_array = np.array(voltages)
        outliers = []
        outlier_indices = []

        if method == 'iqr':
            q25, q75 = np.percentile(voltages_array, [25, 75])
            iqr = q75 - q25
            lower_bound = q25 - threshold * iqr
            upper_bound = q75 + threshold * iqr

            for i, v in enumerate(voltages):
                if v < lower_bound or v > upper_bound:
                    outliers.append(float(v))
                    outlier_indices.append(i)

        elif method == 'zscore':
            z_scores = np.abs((voltages_array - np.mean(voltages_array)) / np.std(voltages_array))
            outlier_indices = [i for i, z in enumerate(z_scores) if z > threshold]
            outliers = [float(voltages[i]) for i in outlier_indices]

        elif method == 'modified_zscore':
            median = np.median(voltages_array)
            mad = np.median(np.abs(voltages_array - median))
            modified_z_scores = 0.6745 * (voltages_array - median) / mad
            outlier_indices = [i for i, z in enumerate(modified_z_scores) if abs(z) > threshold]
            outliers = [float(voltages[i]) for i in outlier_indices]

        return {
            'outliers': outliers,
            'outlier_indices': outlier_indices,
            'outlier_percentage': len(outliers) / len(voltages) * 100,
            'method': method,
            'threshold': threshold
        }

    def calculate_block_statistics(self, voltages: List[float], block_size: int) -> List[Dict[str, Any]]:
        """
        Calcula estadísticas por bloques de datos

        Args:
            voltages: Lista completa de voltajes
            block_size: Tamaño de cada bloque

        Returns:
            Lista de diccionarios con estadísticas por bloque
        """
        if not voltages or not self.numpy_available:
            return []

        block_stats = []
        voltages_array = np.array(voltages)

        for i in range(0, len(voltages), block_size):
            block_data = voltages_array[i:i + block_size]
            if len(block_data) > 0:
                stats = {
                    'block_number': len(block_stats) + 1,
                    'start_index': i,
                    'end_index': min(i + block_size - 1, len(voltages) - 1),
                    'sample_count': len(block_data),
                    'mean': float(np.mean(block_data)),
                    'std': float(np.std(block_data, ddof=1)) if len(block_data) > 1 else 0,
                    'min': float(np.min(block_data)),
                    'max': float(np.max(block_data)),
                    'range': float(np.max(block_data) - np.min(block_data))
                }
                block_stats.append(stats)

        return block_stats

    def get_summary_report(self, stats: Dict[str, Any], sample_count: int = 0) -> str:
        """Genera un reporte resumen de las estadísticas"""
        if not stats:
            return "No hay datos para generar reporte"

        lines = [
            "RESUMEN ESTADÍSTICO",
            "=" * 50,
            "",
            f"Número de muestras: {sample_count:,}",
            f"Media: {stats.get('mean', 0):.6f} V",
            f"Desviación estándar: {stats.get('std', 0):.6f} V",
            f"Varianza: {stats.get('variance', 0):.2e} V²" if abs(stats.get('variance', 0)) < 0.001 else f"Varianza: {stats.get('variance', 0):.6f} V²",
            f"Desviación Media Absoluta: {stats.get('mad', 0):.6f} V",
            f"Rango: {stats.get('range', 0):.6f} V",
            f"Mínimo: {stats.get('min', 0):.6f} V",
            f"Máximo: {stats.get('max', 0):.6f} V",
        ]

        # Agregar estadísticas adicionales si están disponibles
        if 'cv' in stats:
            lines.append(f"Coeficiente de variación: {stats['cv']:.2f}%")
        if 'skewness' in stats:
            lines.append(f"Asimetría: {stats['skewness']:.4f}")
        if 'kurtosis' in stats:
            lines.append(f"Curtosis: {stats['kurtosis']:.4f}")
        if 'autocorr_lag1' in stats:
            lines.append(f"Autocorrelación (lag 1): {stats['autocorr_lag1']:.4f}")
        if 'time_correlation' in stats:
            trend = "tendencia creciente" if stats['time_correlation'] > 0.1 else \
                   "tendencia decreciente" if stats['time_correlation'] < -0.1 else \
                   "sin tendencia clara"
            lines.append(f"Correlación temporal: {stats['time_correlation']:.4f} ({trend})")

        return "\n".join(lines)