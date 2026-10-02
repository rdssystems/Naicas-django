from django.shortcuts import render


def home(request):
    # Provisória: vira o dashboard (com login obrigatório) quando usuarios/ existir.
    return render(request, 'core/home.html')
