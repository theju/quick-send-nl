import io
import re
import csv

from django import forms
from django.utils.translation import gettext as _


EMAIL_HEADER_REGEXP = re.compile(",?e\_mail,?", re.I)


class UploadCSVForm(forms.Form):
    email_field = forms.CharField(required=False)
    csv_file = forms.FileField()

    def clean_csv_file(self):
        csv_file = self.cleaned_data['csv_file']
        csv_file.seek(0)
        cf = csv.DictReader(io.StringIO(csv_file.read().decode()))
        header = cf.fieldnames
        header = list(map(lambda x: x.lower().replace(' ', '_').replace('-', '_'), header))
        cf.fieldnames = header
        email_header_found = False
        for col in header:
            if EMAIL_HEADER_REGEXP.search(col):
                email_header_found = True
                break
        if not email_header_found:
            msg = "Could not locate one of email, e-mail, Email or E-Mail in the header"
            raise forms.ValidationError(_(msg))
        return cf

    def clean(self):
        data = self.cleaned_data
        if not data.get('csv_file'):
            return data
        csv_file = data['csv_file']
        header = csv_file.fieldnames
        for col in header:
            if EMAIL_HEADER_REGEXP.search(col):
                data['email_field'] = col
                break
        return data


class ComposeMessageForm(forms.Form):
    sender = forms.EmailField()
    subject = forms.CharField()
    txt_msg = forms.CharField(required=False)
    html_msg = forms.CharField()


class ModeForm(forms.Form):
    mode = forms.CharField(initial='smtp', required=True)

    def clean_mode(self):
        mode = self.cleaned_data['mode']
        if not mode in ['smtp', 'google']:
            raise forms.ValidationError(
                _("Invalid mode %(value)s"),
                params={'value': mode}
            )
        return mode


class SMTPForm(forms.Form):
    username = forms.CharField()
    password = forms.CharField()
    host     = forms.CharField()
    port     = forms.CharField()
    use_tls  = forms.BooleanField(initial=True)


class GoogleOAuthForm(forms.Form):
    access_token = forms.CharField()
