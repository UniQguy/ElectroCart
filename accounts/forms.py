import re
from django import forms
from django.core.exceptions import ValidationError
from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password
from .models import UserProfile


class CheckoutForm(forms.Form):
    PAYMENT_CHOICES = (
        ('DIRECT_ATELIER', 'Direct Atelier Reconciled Invoice (Complimentary Delivery)'),
        ('RAZORPAY', 'Razorpay UPI & Cards'),
    )

    name = forms.CharField(
        max_length=150,
        min_length=2,
        required=True,
        error_messages={
            'required': 'Recipient name is required.',
            'min_length': 'Recipient name must contain at least 2 characters.'
        },
        widget=forms.TextInput(attrs={
            'placeholder': 'e.g. Adarsh Patel',
            'autocomplete': 'name',
            'class': 'atelier-input'
        })
    )

    email = forms.EmailField(
        required=True,
        error_messages={
            'required': 'Dispatch notification email is required.',
            'invalid': 'Please enter a valid email address.'
        },
        widget=forms.EmailInput(attrs={
            'placeholder': 'client@atelier.in',
            'autocomplete': 'email',
            'class': 'atelier-input'
        })
    )

    address = forms.CharField(
        min_length=5,
        max_length=500,
        required=True,
        error_messages={
            'required': 'Physical street address is required for courier dispatch.',
            'min_length': 'Please provide a complete street address (minimum 5 characters).'
        },
        widget=forms.TextInput(attrs={
            'placeholder': 'e.g. 402 Hardware Labs, C.G. Road',
            'autocomplete': 'street-address',
            'class': 'atelier-input'
        })
    )

    city = forms.CharField(
        max_length=100,
        min_length=2,
        required=True,
        error_messages={
            'required': 'City / Municipality is required.',
            'min_length': 'City must contain at least 2 characters.'
        },
        widget=forms.TextInput(attrs={
            'placeholder': 'e.g. Ahmedabad',
            'autocomplete': 'address-level2',
            'class': 'atelier-input'
        })
    )

    state = forms.CharField(
        max_length=100,
        min_length=2,
        required=True,
        error_messages={
            'required': 'State / Territory is required.',
            'min_length': 'State must contain at least 2 characters.'
        },
        widget=forms.TextInput(attrs={
            'placeholder': 'e.g. Gujarat',
            'autocomplete': 'address-level1',
            'class': 'atelier-input'
        })
    )

    pincode = forms.CharField(
        max_length=10,
        min_length=6,
        required=True,
        error_messages={
            'required': 'Postal PIN code is required.',
        },
        widget=forms.TextInput(attrs={
            'placeholder': '380009',
            'autocomplete': 'postal-code',
            'inputmode': 'numeric',
            'pattern': '[0-9]{6}',
            'class': 'atelier-input'
        })
    )

    phone = forms.CharField(
        max_length=20,
        min_length=10,
        required=True,
        error_messages={
            'required': 'Contact mobile number is required for delivery OTP.',
        },
        widget=forms.TextInput(attrs={
            'placeholder': '9876543210',
            'autocomplete': 'tel',
            'inputmode': 'tel',
            'class': 'atelier-input'
        })
    )

    payment_method = forms.ChoiceField(
        choices=PAYMENT_CHOICES,
        initial='DIRECT_ATELIER',
        required=True
    )

    def clean_name(self):
        name = self.cleaned_data.get('name', '').strip()
        if not name:
            raise ValidationError('Recipient name cannot be blank.')
        return name

    def clean_address(self):
        address = self.cleaned_data.get('address', '').strip()
        if not address:
            raise ValidationError('Street address cannot be blank.')
        return address

    def clean_city(self):
        return self.cleaned_data.get('city', '').strip()

    def clean_state(self):
        return self.cleaned_data.get('state', '').strip()

    def clean_pincode(self):
        pin = self.cleaned_data.get('pincode', '').strip().replace(' ', '')
        if not re.match(r'^[1-9][0-9]{5}$', pin):
            raise ValidationError('Please enter a valid 6-digit Indian postal PIN code.')
        return pin

    def clean_phone(self):
        phone = self.cleaned_data.get('phone', '').strip().replace(' ', '').replace('-', '')
        if phone.startswith('+91'):
            phone = phone[3:]
        elif phone.startswith('0'):
            phone = phone[1:]

        if not re.match(r'^[6-9][0-9]{9}$', phone):
            raise ValidationError('Please enter a valid 10-digit Indian mobile number (e.g. 9876543210).')
        return phone


class AddressUpdateForm(forms.ModelForm):
    class Meta:
        model = UserProfile
        fields = ['phone', 'address', 'city', 'state', 'pincode']

    def clean_pincode(self):
        pin = self.cleaned_data.get('pincode', '').strip().replace(' ', '')
        if pin and not re.match(r'^[1-9][0-9]{5}$', pin):
            raise ValidationError('Please enter a valid 6-digit Indian postal PIN code.')
        return pin

    def clean_phone(self):
        phone = self.cleaned_data.get('phone', '').strip().replace(' ', '').replace('-', '')
        if phone:
            if phone.startswith('+91'):
                phone = phone[3:]
            elif phone.startswith('0'):
                phone = phone[1:]
            if not re.match(r'^[6-9][0-9]{9}$', phone):
                raise ValidationError('Please enter a valid 10-digit Indian mobile number.')
        return phone


class SignUpForm(forms.Form):
    username = forms.CharField(
        max_length=150,
        min_length=3,
        required=True,
        error_messages={
            'required': 'Username is required.',
            'min_length': 'Username must be at least 3 characters.'
        }
    )
    email = forms.EmailField(
        required=True,
        error_messages={
            'required': 'Email is required.',
            'invalid': 'Please enter a valid email address.'
        }
    )
    password = forms.CharField(
        widget=forms.PasswordInput,
        required=True,
        min_length=8
    )
    confirm_password = forms.CharField(
        widget=forms.PasswordInput,
        required=True
    )

    def clean_username(self):
        username = self.cleaned_data.get('username', '').strip()
        if not re.match(r'^[a-zA-Z0-9_.-]+$', username):
            raise ValidationError('Username may only contain letters, numbers, dots, hyphens, and underscores.')
        if User.objects.filter(username__iexact=username).exists():
            raise ValidationError('An account with this username already exists.')
        return username

    def clean_email(self):
        email = self.cleaned_data.get('email', '').strip().lower()
        if User.objects.filter(email__iexact=email).exists():
            raise ValidationError('An account with this email address already exists.')
        return email

    def clean(self):
        cleaned_data = super().clean()
        p1 = cleaned_data.get('password')
        p2 = cleaned_data.get('confirm_password')

        if p1 and p2 and p1 != p2:
            self.add_error('confirm_password', 'Passwords do not match.')

        if p1:
            try:
                validate_password(p1)
            except ValidationError as error:
                self.add_error('password', error)

        return cleaned_data

