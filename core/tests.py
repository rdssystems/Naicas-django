from django.test import TestCase
from django.urls import reverse


class HomeTests(TestCase):
    def test_home_responde(self):
        response = self.client.get(reverse('core:home'))
        self.assertEqual(response.status_code, 200)
