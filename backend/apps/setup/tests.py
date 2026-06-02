from django.test import TestCase

from apps.setup.models import (
    Administration,
    Insurance,
    InsuranceClass,
    Nationality,
    Profession,
    Sponsorship,
    SystemSettings,
)


class SetupLookupModelTests(TestCase):
    def test_administration_str(self):
        a = Administration.objects.create(code='ADM01', name='الموارد البشرية')
        self.assertIn('ADM01', str(a))
        self.assertIn('الموارد البشرية', str(a))

    def test_nationality_str_and_ordering(self):
        n = Nationality.objects.create(code='NAT01', name='سعودي')
        self.assertEqual(str(n), 'سعودي')

    def test_profession_unique_code(self):
        Profession.objects.create(code='JOB01', name='محاسب')
        with self.assertRaises(Exception):
            Profession.objects.create(code='JOB01', name='آخر')

    def test_sponsorship_name_property(self):
        s = Sponsorship.objects.create(code='SP01', company_name='شركة الكفالة')
        self.assertEqual(s.name, 'شركة الكفالة')
        self.assertEqual(str(s), 'شركة الكفالة')

    def test_insurance_name_property(self):
        ins = Insurance.objects.create(code='INS01', insurance_type='تأمين طبي')
        self.assertEqual(ins.name, 'تأمين طبي')

    def test_insurance_class_str(self):
        ic = InsuranceClass.objects.create(code='IC01', class_type='فئة أ')
        self.assertIn('فئة أ', str(ic))

    def test_system_settings_str(self):
        s = SystemSettings.objects.create(key='site_name', value='HR ERP')
        self.assertEqual(str(s), 'site_name')

    def test_soft_delete_hides_from_default_manager(self):
        n = Nationality.objects.create(code='NAT-DEL', name='مؤقت')
        n.delete()
        self.assertFalse(Nationality.objects.filter(pk=n.pk).exists())
        self.assertTrue(Nationality.all_objects.filter(pk=n.pk, is_deleted=True).exists())
