"""
Tests unitarios para el sistema Keithley
"""
import unittest
import tempfile
import os
from unittest.mock import Mock, patch, MagicMock
import sys
import csv

# Agregar el directorio actual al path para importar módulos locales
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import KeithleyConfig
from analysis import StatisticalAnalyzer
from plotting import KeithleyPlotter


class TestKeithleyConfig(unittest.TestCase):
    """Tests para la configuración del sistema"""

    def setUp(self):
        self.config = KeithleyConfig()

    def test_default_values(self):
        """Test valores por defecto"""
        args = self.config.parser.parse_args([])
        self.assertEqual(args.label, 'experimento')
        self.assertEqual(args.samples, 2000)
        self.assertEqual(args.nplc, '10')
        self.assertEqual(args.blocks, 50)
        self.assertFalse(args.force)
        self.assertFalse(args.no_stats)

    def test_valid_config(self):
        """Test configuración válida"""
        test_args = [
            '--label', 'test_experiment',
            '--samples', '1000',
            '--nplc', '1',
            '--blocks', '10'
        ]
        args = self.config.parser.parse_args(test_args)
        self.config.args = args

        valid, error = self.config.validate_config()
        self.assertTrue(valid)
        self.assertIsNone(error)

    def test_invalid_samples(self):
        """Test validación de muestras inválidas"""
        test_args = ['--samples', '50']  # Menos del mínimo
        args = self.config.parser.parse_args(test_args)
        self.config.args = args

        valid, error = self.config.validate_config()
        self.assertFalse(valid)
        self.assertIn("100-2000", error)

    def test_invalid_nplc(self):
        """Test validación de NPLC inválido"""
        test_args = ['--nplc', '200']  # Fuera del rango válido
        args = self.config.parser.parse_args(test_args)
        self.config.args = args

        valid, error = self.config.validate_config()
        self.assertFalse(valid)
        self.assertIn("NPLCycles", error)

    def test_force_nplc(self):
        """Test uso de --force para NPLC personalizado"""
        test_args = ['--nplc', '50', '--force']
        args = self.config.parser.parse_args(test_args)
        self.config.args = args

        valid, error = self.config.validate_config()
        self.assertTrue(valid)  # Debe ser válido con --force

    def test_processed_config(self):
        """Test configuración procesada"""
        test_args = [
            '--label', 'processed_test',
            '--samples', '1500',
            '--nplc', '2',
            '--blocks', '25',
            '--force',
            '--no-stats'
        ]
        args = self.config.parser.parse_args(test_args)
        self.config.args = args

        config_dict = self.config.get_processed_config()

        self.assertEqual(config_dict['experiment_label'], 'processed_test')
        self.assertEqual(config_dict['samples_per_count'], 1500)
        self.assertEqual(config_dict['nplc_cycles'], 2.0)
        self.assertEqual(config_dict['num_blocks'], 25)
        self.assertTrue(config_dict['force_nplc'])
        self.assertTrue(config_dict['no_stats'])


class TestStatisticalAnalyzer(unittest.TestCase):
    """Tests para el analizador estadístico"""

    def setUp(self):
        # Datos de prueba
        self.test_data = [1.0, 2.0, 3.0, 4.0, 5.0, 2.5, 3.5, 1.5, 4.5, 2.0]
        self.analyzer = StatisticalAnalyzer(numpy_available=True, scipy_available=True)

    def test_calculate_basic_stats(self):
        """Test cálculo de estadísticas básicas"""
        stats = self.analyzer.calculate_comprehensive_stats(self.test_data)

        self.assertIn('mean', stats)
        self.assertIn('std', stats)
        self.assertIn('min', stats)
        self.assertIn('max', stats)

        # Verificar algunos valores conocidos
        self.assertAlmostEqual(stats['mean'], 2.9, places=2)  # Corregido: promedio real de los datos
        self.assertEqual(stats['min'], 1.0)
        self.assertEqual(stats['max'], 5.0)

    def test_empty_data(self):
        """Test con datos vacíos"""
        stats = self.analyzer.calculate_comprehensive_stats([])
        self.assertEqual(stats, {})

    def test_detect_outliers_iqr(self):
        """Test detección de outliers usando IQR"""
        # Agregar algunos outliers
        data_with_outliers = self.test_data + [100.0, -50.0]

        outlier_info = self.analyzer.detect_outliers(data_with_outliers, method='iqr')

        self.assertIn('outliers', outlier_info)
        self.assertIn('outlier_indices', outlier_info)
        self.assertGreater(len(outlier_info['outliers']), 0)

    def test_block_statistics(self):
        """Test estadísticas por bloque"""
        block_stats = self.analyzer.calculate_block_statistics(self.test_data, block_size=3)

        self.assertGreater(len(block_stats), 0)

        # Verificar estructura del primer bloque
        first_block = block_stats[0]
        self.assertIn('block_number', first_block)
        self.assertIn('mean', first_block)
        self.assertIn('std', first_block)
        self.assertIn('sample_count', first_block)

    def test_summary_report(self):
        """Test generación de reporte resumen"""
        stats = self.analyzer.calculate_comprehensive_stats(self.test_data)
        report = self.analyzer.get_summary_report(stats, len(self.test_data))

        self.assertIn("RESUMEN ESTADÍSTICO", report)
        self.assertIn("Media:", report)
        self.assertIn("Desviación estándar:", report)


class TestKeithleyPlotter(unittest.TestCase):
    """Tests para el generador de gráficas"""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.plotter = KeithleyPlotter(output_dir=self.temp_dir, experiment_label='test')

        # Datos de prueba
        self.test_plot_data = [
            {'global_sample': 1, 'voltage': 1.0, 'block': 1},
            {'global_sample': 2, 'voltage': 2.0, 'block': 1},
            {'global_sample': 3, 'voltage': 3.0, 'block': 1},
            {'global_sample': 4, 'voltage': 1.5, 'block': 2},
            {'global_sample': 5, 'voltage': 2.5, 'block': 2},
        ]

    def tearDown(self):
        # Limpiar archivos temporales
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    @patch('matplotlib.pyplot.savefig')
    @patch('matplotlib.pyplot.show')
    @patch('matplotlib.pyplot.figure')
    @patch('matplotlib.pyplot.subplot')
    @patch('matplotlib.pyplot.plot')
    def test_create_basic_plot(self, mock_plot, mock_subplot, mock_figure, mock_show, mock_savefig):
        """Test creación de gráfica básica"""
        # Mock básico para evitar dependencias de matplotlib
        mock_fig = Mock()
        mock_figure.return_value = mock_fig

        result = self.plotter.create_basic_plot(self.test_plot_data)

        # Verificar que se llamó a savefig
        mock_savefig.assert_called_once()
        self.assertIn('basic', result)
        self.assertIn('test', result)

    @patch('matplotlib.pyplot.savefig')
    @patch('matplotlib.pyplot.show')
    @patch('matplotlib.pyplot.figure')
    @patch('matplotlib.pyplot.subplot')
    @patch('matplotlib.pyplot.plot')
    def test_create_comprehensive_plot(self, mock_plot, mock_subplot, mock_figure, mock_show, mock_savefig):
        """Test creación de gráfica completa"""
        # Mock básico para evitar dependencias de matplotlib
        mock_fig = Mock()
        mock_fig.get_axes.return_value = []  # Evitar el error de iteración
        mock_figure.return_value = mock_fig

        # Calcular estadísticas para la prueba
        analyzer = StatisticalAnalyzer()
        stats = analyzer.calculate_comprehensive_stats([d['voltage'] for d in self.test_plot_data])

        result = self.plotter.create_comprehensive_plot(self.test_plot_data, stats)

        # Verificar que se llamó a savefig
        mock_savefig.assert_called_once()
        self.assertIn('analysis', result)
        self.assertIn('test', result)


class TestDataValidation(unittest.TestCase):
    """Tests para validación de datos"""

    def test_csv_format_validation(self):
        """Test validación de formato CSV"""
        # Crear archivo CSV temporal
        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as f:
            writer = csv.writer(f)
            writer.writerow(['Block', 'Sample_In_Block', 'Global_Sample', 'Voltage_V', 'Timestamp'])
            writer.writerow([1, 1, 1, 2.5, '2024-01-01T12:00:00'])
            writer.writerow([1, 2, 2, 2.7, '2024-01-01T12:00:01'])
            temp_file = f.name

        try:
            # Leer y validar
            with open(temp_file, 'r') as f:
                reader = csv.DictReader(f)
                rows = list(reader)

            self.assertEqual(len(rows), 2)

            # Validar estructura
            for row in rows:
                self.assertIn('Block', row)
                self.assertIn('Voltage_V', row)
                # Validar que el voltaje sea numérico
                voltage = float(row['Voltage_V'])
                self.assertIsInstance(voltage, float)

        finally:
            os.unlink(temp_file)

    def test_voltage_range_validation(self):
        """Test validación de rangos de voltaje"""
        # Voltajes típicos de Keithley (rango razonable)
        valid_voltages = [0.001, 1.0, 10.0, -1.0, -0.001]
        invalid_voltages = [1000.0, -1000.0, 1e6, -1e6]  # Fuera de rango típico

        for v in valid_voltages:
            self.assertGreaterEqual(v, -100.0)
            self.assertLessEqual(v, 100.0)

        # Nota: En un sistema real, se validarían contra especificaciones del instrumento
        for v in invalid_voltages:
            # Solo verificar que están fuera del rango esperado típico
            self.assertTrue(abs(v) > 100.0 or abs(v) < 1e-6)


if __name__ == '__main__':
    # Configurar logging para tests
    import logging
    logging.basicConfig(level=logging.WARNING)

    # Ejecutar tests
    unittest.main(verbosity=2)