# -*- coding: utf-8 -*-
"""
Created on Thu May  7 15:26:10 2026

@author: USER}
"""
import datetime

def calcular_proximo_repaso(calidad_respuesta, ease_factor_actual, repeticiones_actual, intervalo_actual):
    """
    calidad_respuesta: 0 (olvido total) a 5 (perfecto)
    """
    # Si la respuesta es mala (menor a 3), reiniciamos el ciclo
    if calidad_respuesta < 3:
        nuevo_intervalo = 1
        nuevas_repeticiones = 0
    else:
        if repeticiones_actual == 0:
            nuevo_intervalo = 1
        elif repeticiones_actual == 1:
            nuevo_intervalo = 6
        else:
            nuevo_intervalo = round(intervalo_actual * ease_factor_actual)
        
        nuevas_repeticiones = repeticiones_actual + 1

    # Actualizar el Ease Factor (Factor de facilidad)
    nuevo_ef = ease_factor_actual + (0.1 - (5 - calidad_respuesta) * (0.08 + (5 - calidad_respuesta) * 0.02))
    
    # El EF nunca debe ser menor a 1.3
    if nuevo_ef < 1.3:
        nuevo_ef = 1.3
        
    proxima_fecha = datetime.datetime.now() + datetime.timedelta(days=nuevo_intervalo)
    
    return nuevo_intervalo, nuevas_repeticiones, nuevo_ef, proxima_fecha
