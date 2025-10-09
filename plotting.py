"""
Módulo de visualización para datos Keithley
"""
from typing import List, Dict, Any, Optional
import matplotlib.pyplot as plt
from datetime import datetime
import os


class KeithleyPlotter:
    """Clase para generar gráficas de análisis de datos Keithley"""

    def __init__(self, output_dir: str = ".", experiment_label: str = "experimento"):
        self.output_dir = output_dir
        self.experiment_label = experiment_label

        # Crear directorio de salida si no existe
        if not os.path.exists(self.output_dir):
            os.makedirs(self.output_dir, exist_ok=True)

        self._setup_plot_style()

    def _setup_plot_style(self):
        """Configura el estilo de las gráficas"""
        plt.rcParams.update({
            'figure.figsize': (16, 12),
            'font.size': 10,
            'axes.labelsize': 12,
            'axes.titlesize': 14,
            'xtick.labelsize': 10,
            'ytick.labelsize': 10,
            'legend.fontsize': 10,
            'figure.dpi': 100,
            'savefig.dpi': 300,
            'savefig.bbox': 'tight'
        })

    def create_comprehensive_plot(self, plot_data: List[Dict], stats: Dict[str, Any],
                                block_stats: Optional[List[Dict]] = None) -> str:
        """
        Crea una gráfica completa con múltiples análisis

        Args:
            plot_data: Lista de diccionarios con datos de voltaje por muestra
            stats: Estadísticas calculadas
            block_stats: Estadísticas por bloque (opcional)

        Returns:
            Nombre del archivo de la gráfica guardada
        """
        fig = plt.figure(figsize=(16, 12))

        # Extraer datos
        sample_indices = [d['global_sample'] for d in plot_data]
        voltages = [d['voltage'] for d in plot_data]
        blocks = list(set(d['block'] for d in plot_data))

        # Subplot 1: Serie temporal completa
        plt.subplot(3, 2, 1)
        self._plot_time_series(sample_indices, voltages, stats)

        # Subplot 2: Distribución con histograma y KDE
        plt.subplot(3, 2, 2)
        self._plot_distribution(voltages, stats)

        # Subplot 3: Estadísticas por bloque
        plt.subplot(3, 2, 3)
        if block_stats:
            self._plot_block_statistics(block_stats)
        else:
            self._plot_simple_block_stats(plot_data)

        # Subplot 4: Autocorrelación
        plt.subplot(3, 2, 4)
        self._plot_autocorrelation(voltages, stats)

        # Subplot 5: Análisis de estabilidad
        plt.subplot(3, 2, 5)
        self._plot_stability_analysis(voltages, stats)

        # Subplot 6: Resumen estadístico
        plt.subplot(3, 2, 6)
        self._plot_statistics_summary(stats, len(voltages))

        plt.tight_layout()

        # Guardar gráfica
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f'voltage_analysis_{self.experiment_label}_{timestamp}.png'
        filepath = os.path.join(self.output_dir, filename)

        plt.savefig(filepath, dpi=300, bbox_inches='tight')
        plt.close(fig)

        return filepath

    def create_basic_plot(self, plot_data: List[Dict]) -> str:
        """
        Crea una gráfica básica con serie temporal e histograma

        Args:
            plot_data: Lista de diccionarios con datos de voltaje

        Returns:
            Nombre del archivo de la gráfica guardada
        """
        fig = plt.figure(figsize=(12, 5))

        # Extraer datos
        sample_indices = [d['global_sample'] for d in plot_data]
        voltages = [d['voltage'] for d in plot_data]

        # Subplot 1: Serie temporal básica
        plt.subplot(1, 2, 1)
        plt.plot(sample_indices, voltages, 'b-', alpha=0.7, linewidth=1)
        plt.xlabel('Muestra Global')
        plt.ylabel('Voltaje (V)')
        plt.title(f'Datos de Voltaje - {len(plot_data)} muestras')
        plt.grid(True, alpha=0.3)

        # Subplot 2: Histograma básico
        plt.subplot(1, 2, 2)
        plt.hist(voltages, bins=30, alpha=0.7, color='skyblue', edgecolor='black')
        plt.xlabel('Voltaje (V)')
        plt.ylabel('Frecuencia')
        plt.title('Distribución de Voltajes')
        plt.grid(True, alpha=0.3)

        plt.tight_layout()

        # Guardar gráfica
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f'voltage_analysis_basic_{self.experiment_label}_{timestamp}.png'
        filepath = os.path.join(self.output_dir, filename)

        plt.savefig(filepath, dpi=300, bbox_inches='tight')
        plt.close(fig)

        return filepath

    def _plot_time_series(self, sample_indices: List[int], voltages: List[float],
                         stats: Dict[str, Any]):
        """Grafica la serie temporal completa con estadísticas"""
        plt.plot(sample_indices, voltages, 'b-', alpha=0.7, linewidth=1, label='Datos')

        # Líneas de referencia
        if 'mean' in stats:
            plt.axhline(y=stats['mean'], color='r', linestyle='--', alpha=0.8,
                       label=f'Media: {stats["mean"]:.6f}V')

        if 'std' in stats and 'mean' in stats:
            plt.axhline(y=stats['mean'] + stats['std'], color='orange', linestyle=':', alpha=0.6,
                       label=f'+1σ: {stats["mean"] + stats["std"]:.6f}V')
            plt.axhline(y=stats['mean'] - stats['std'], color='orange', linestyle=':', alpha=0.6,
                       label=f'-1σ: {stats["mean"] - stats["std"]:.6f}V')

        plt.xlabel('Muestra Global')
        plt.ylabel('Voltaje (V)')
        plt.title(f'Serie Temporal Completa - {len(voltages)} muestras')
        plt.grid(True, alpha=0.3)
        plt.legend()

    def _plot_distribution(self, voltages: List[float], stats: Dict[str, Any]):
        """Grafica la distribución con histograma y KDE"""
        try:
            import numpy as np
            from scipy import stats as scipy_stats

            # Histograma con KDE
            plt.hist(voltages, bins=50, alpha=0.7, color='skyblue', edgecolor='black',
                    density=True, label='Histograma')

            # Línea de densidad usando scipy
            kde = scipy_stats.gaussian_kde(voltages)
            x_range = np.linspace(min(voltages), max(voltages), 100)
            plt.plot(x_range, kde(x_range), 'r-', linewidth=2, label='Densidad KDE')

        except ImportError:
            # Histograma básico sin KDE
            plt.hist(voltages, bins=30, alpha=0.7, color='skyblue', edgecolor='black',
                    label='Histograma')

        # Línea de media
        if 'mean' in stats:
            plt.axvline(x=stats['mean'], color='red', linestyle='--', linewidth=2,
                       label=f'Media: {stats["mean"]:.6f}V')

        plt.xlabel('Voltaje (V)')
        plt.ylabel('Densidad de Probabilidad')
        plt.title('Distribución de Voltajes')
        plt.grid(True, alpha=0.3)
        plt.legend()

    def _plot_block_statistics(self, block_stats: List[Dict]):
        """Grafica estadísticas por bloque usando datos precalculados"""
        if not block_stats:
            return

        blocks = [bs['block_number'] for bs in block_stats]
        means = [bs['mean'] for bs in block_stats]
        stds = [bs['std'] for bs in block_stats]

        plt.errorbar(blocks, means, yerr=stds, fmt='ro-', capsize=3, alpha=0.7,
                    label='Media ± σ')
        plt.xlabel('Número de Bloque')
        plt.ylabel('Voltaje (V)')
        plt.title('Estadísticas por Bloque')
        plt.grid(True, alpha=0.3)
        plt.legend()

    def _plot_simple_block_stats(self, plot_data: List[Dict]):
        """Grafica estadísticas simples por bloque"""
        try:
            import numpy as np

            blocks = sorted(list(set(d['block'] for d in plot_data)))
            block_means = []
            block_stds = []

            for block in blocks:
                block_voltages = [d['voltage'] for d in plot_data if d['block'] == block]
                if block_voltages:
                    block_array = np.array(block_voltages)
                    mean_val = np.mean(block_array)
                    std_val = np.std(block_array, ddof=1) if len(block_array) > 1 else 0
                    block_means.append(mean_val)
                    block_stds.append(std_val)

            plt.errorbar(blocks, block_means, yerr=block_stds, fmt='ro-', capsize=3, alpha=0.7,
                        label='Media ± σ')
            plt.xlabel('Número de Bloque')
            plt.ylabel('Voltaje (V)')
            plt.title('Estadísticas por Bloque')
            plt.grid(True, alpha=0.3)
            plt.legend()

        except ImportError:
            plt.text(0.5, 0.5, 'NumPy requerido para\ngráficas por bloque',
                    transform=plt.gca().transAxes, ha='center', va='center', fontsize=12)
            plt.title('Estadísticas por Bloque (No disponible)')

    def _plot_autocorrelation(self, voltages: List[float], stats: Dict[str, Any]):
        """Grafica la función de autocorrelación"""
        try:
            import numpy as np

            if len(voltages) > 10:
                max_lag = min(50, len(voltages) // 4)
                autocorr = []

                for lag in range(1, max_lag + 1):
                    if len(voltages) > lag:
                        corr = np.corrcoef(voltages[:-lag], voltages[lag:])[0, 1]
                        autocorr.append(corr)

                plt.plot(range(1, len(autocorr) + 1), autocorr, 'g-o', alpha=0.7,
                        markersize=3)
                plt.axhline(y=0, color='black', linestyle='-', alpha=0.3)

                # Línea de significancia
                n = len(voltages)
                significance_level = 1.96 / np.sqrt(n)
                plt.axhline(y=significance_level, color='red', linestyle='--', alpha=0.5,
                           label='95% significancia')
                plt.axhline(y=-significance_level, color='red', linestyle='--', alpha=0.5)

                plt.xlabel('Lag (muestras)')
                plt.ylabel('Autocorrelación')
                plt.title('Función de Autocorrelación')
                plt.grid(True, alpha=0.3)
                plt.legend()
            else:
                plt.text(0.5, 0.5, 'Datos insuficientes\npara autocorrelación',
                        transform=plt.gca().transAxes, ha='center', va='center', fontsize=12)
                plt.title('Autocorrelación (Datos insuficientes)')

        except ImportError:
            plt.text(0.5, 0.5, 'NumPy requerido para\nautocorrelación',
                    transform=plt.gca().transAxes, ha='center', va='center', fontsize=12)
            plt.title('Autocorrelación (No disponible)')

    def _plot_stability_analysis(self, voltages: List[float], stats: Dict[str, Any]):
        """Grafica análisis de estabilidad temporal"""
        try:
            import numpy as np

            if len(voltages) > 100:
                window_size = max(50, len(voltages) // 20)
                moving_mean = []
                moving_std = []
                positions = []

                for i in range(window_size, len(voltages), window_size // 2):
                    window = voltages[i-window_size:i]
                    if len(window) > 10:
                        moving_mean.append(np.mean(window))
                        moving_std.append(np.std(window, ddof=1))
                        positions.append(i)

                if moving_mean:
                    plt.plot(positions, moving_mean, 'purple', linewidth=2, label='Media móvil')
                    plt.fill_between(positions,
                                   [m - s for m, s in zip(moving_mean, moving_std)],
                                   [m + s for m, s in zip(moving_mean, moving_std)],
                                   alpha=0.3, color='purple', label='±σ móvil')
                    plt.xlabel('Posición en la serie')
                    plt.ylabel('Voltaje (V)')
                    plt.title(f'Estabilidad (Ventana: {window_size} muestras)')
                    plt.grid(True, alpha=0.3)
                    plt.legend()
                else:
                    plt.text(0.5, 0.5, 'Datos insuficientes\npara análisis de estabilidad',
                            transform=plt.gca().transAxes, ha='center', va='center', fontsize=12)
            else:
                plt.text(0.5, 0.5, 'Datos insuficientes\npara análisis de estabilidad',
                        transform=plt.gca().transAxes, ha='center', va='center', fontsize=12)

            plt.title('Análisis de Estabilidad')

        except ImportError:
            plt.text(0.5, 0.5, 'NumPy requerido para\nanálisis de estabilidad',
                    transform=plt.gca().transAxes, ha='center', va='center', fontsize=12)
            plt.title('Análisis de Estabilidad (No disponible)')

    def _plot_statistics_summary(self, stats: Dict[str, Any], sample_count: int):
        """Muestra un resumen estadístico en formato tabla"""
        plt.axis('off')

        # Crear tabla de estadísticas
        stats_text = ".2e" if abs(stats.get('variance', 0)) < 0.001 else ".6f"
        summary_text = ".1f" if abs(stats.get('variance', 0)) < 0.001 else ".6f"

        stats_info = [
            "Estadísticas del Conjunto de Datos",
            "=" * 35,
            "",
            f"Número de muestras: {sample_count:,}",
            f"Media: {stats.get('mean', 0):.6f} V",
            f"Desviación estándar: {stats.get('std', 0):.6f} V",
            f"Varianza: {stats.get('variance', 0):{stats_text}} V²",
            f"Desviación Media Absoluta: {stats.get('mad', 0):.6f} V",
            f"Rango: {stats.get('range', 0):.6f} V",
            f"Mínimo: {stats.get('min', 0):.6f} V",
            f"Máximo: {stats.get('max', 0):.6f} V",
        ]

        # Agregar estadísticas adicionales
        if 'cv' in stats:
            stats_info.append(f"Coeficiente de variación: {stats['cv']:.2f}%")
        if 'skewness' in stats:
            stats_info.append(f"Asimetría: {stats['skewness']:.4f}")
        if 'kurtosis' in stats:
            stats_info.append(f"Curtosis: {stats['kurtosis']:.4f}")
        if 'autocorr_lag1' in stats:
            stats_info.append(f"Autocorrelación (lag 1): {stats['autocorr_lag1']:.4f}")
        if 'time_correlation' in stats:
            trend_desc = "tendencia creciente" if stats['time_correlation'] > 0.1 else \
                        "tendencia decreciente" if stats['time_correlation'] < -0.1 else \
                        "sin tendencia clara"
            stats_info.append(f"Correlación temporal: {stats['time_correlation']:.4f} ({trend_desc})")

        plt.text(0.05, 0.95, '\n'.join(stats_info), transform=plt.gca().transAxes,
                fontsize=9, verticalalignment='top', fontfamily='monospace',
                bbox=dict(boxstyle="round,pad=0.5", facecolor="lightgray", alpha=0.8))