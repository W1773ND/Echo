from django import forms

from echo.models import CSVFile


class CSVFileForm(forms.ModelForm):
    class Meta:
        model = CSVFile
        fields = ('file',)
