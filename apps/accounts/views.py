from django.shortcuts import render, redirect
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth import login, authenticate, logout
from django.contrib import messages
from django import forms
from django.contrib.auth.views import LogoutView
from django.urls import reverse_lazy


class SignUpForm(UserCreationForm):
    email = forms.EmailField(max_length=254, required=True)

    class Meta:
        from django.contrib.auth.models import User
        model = User
        fields = ('username', 'email', 'password1', 'password2')


def signup(request):
    if request.method == 'POST':
        form = SignUpForm(request.POST)
        if form.is_valid():
            user = form.save()
            username = form.cleaned_data.get('username')
            raw_password = form.cleaned_data.get('password1')
            user = authenticate(username=username, password=raw_password)
            login(request, user)
            messages.success(request, "Account created successfully. Welcome to PCR Datenbank!")
            return redirect('core:inventory')
    else:
        form = SignUpForm()
    return render(request, 'registration/signup.html', {'form': form})

def custom_logout(request):
    logout(request)
    messages.success(request, "You have successfully logged out.")
    return redirect('login')