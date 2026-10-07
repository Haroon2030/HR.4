from decimal import Decimal

from django.test import SimpleTestCase

from apps.core.utils.arabic_amount import amount_in_words


class AmountInWordsTests(SimpleTestCase):
    def test_common_amounts(self):
        cases = {
            '5000': 'خمسة آلاف ريال سعودي فقط لا غير',
            '1000': 'ألف ريال سعودي فقط لا غير',
            '2000': 'ألفان ريال سعودي فقط لا غير',
            '2500': 'ألفان وخمسمائة ريال سعودي فقط لا غير',
            '12345': 'اثنا عشر ألف وثلاثمائة وخمسة وأربعون ريال سعودي فقط لا غير',
            '100': 'مائة ريال سعودي فقط لا غير',
            '21': 'واحد وعشرون ريال سعودي فقط لا غير',
            '1500000': 'مليون وخمسمائة ألف ريال سعودي فقط لا غير',
            '0': 'صفر ريال سعودي فقط لا غير',
        }
        for value, expected in cases.items():
            self.assertEqual(amount_in_words(value), expected, value)

    def test_halalas(self):
        self.assertEqual(
            amount_in_words(Decimal('150.50')),
            'مائة وخمسون ريال سعودي وخمسون هللة فقط لا غير',
        )

    def test_invalid_values_return_empty(self):
        self.assertEqual(amount_in_words('abc'), '')
        self.assertEqual(amount_in_words(-5), '')
        self.assertEqual(amount_in_words(None), '')
