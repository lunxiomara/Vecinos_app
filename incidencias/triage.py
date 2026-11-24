import re


REGLAS_CATEGORIA = {
    "agua": [
        "fuga", "filtracion", "filtración", "tuberia", "tubería",
        "agua", "humedad", "caneria", "cañería", "inundacion", "inundación",
    ],
    "electricidad": [
        "luz", "luminaria", "bombillo", "corto", "electrico", "eléctrico",
        "tablero", "breaker", "apagon", "apagón", "chispas", "toma",
    ],
    "seguridad": [
        "porton", "portón", "chapa", "cerradura", "camara", "cámara",
        "alarma", "robo", "acceso", "porteria", "portería", "vigilancia",
    ],
    "limpieza": [
        "basura", "residuos", "aseo", "limpieza", "escombros",
        "mancha", "sucio", "recoleccion", "recolección", "olor",
    ],
}

TERMINOS_PRIORIDAD_ALTA = [
    "fuga", "inundacion", "inundación", "corto", "chispas", "incendio",
    "robo", "emergencia", "peligro", "sin agua", "sin luz", "bloqueado",
]

TERMINOS_PRIORIDAD_MEDIA = [
    "fallo", "falla", "no abre", "danada", "dañada", "filtracion",
    "filtración", "humedad", "dano", "daño", "intermitente", "ruido",
]


def _normalizar(texto: str) -> str:
    texto = (texto or "").lower()
    return re.sub(r"\s+", " ", texto).strip()


def evaluar_incidencia(titulo: str, descripcion: str = "") -> dict:
    texto = _normalizar(f"{titulo} {descripcion}")

    puntajes_categoria = {cat: 0 for cat in REGLAS_CATEGORIA}
    coincidencias_categoria = {cat: [] for cat in REGLAS_CATEGORIA}

    for categoria, palabras in REGLAS_CATEGORIA.items():
        for palabra in palabras:
            if palabra in texto:
                puntajes_categoria[categoria] += 1
                coincidencias_categoria[categoria].append(palabra)

    mejor_categoria = max(puntajes_categoria, key=puntajes_categoria.get)
    max_puntos = puntajes_categoria[mejor_categoria]

    if max_puntos == 0:
        categoria_final = "otros"
        confianza = 0.45
        motivo_cat = "Sin palabras clave coincidentes; asignada a 'otros'."
    else:
        categoria_final = mejor_categoria
        confianza = min(0.95, round(0.60 + 0.15 * max_puntos, 2))
        motivo_cat = f"Coincidencias en '{categoria_final}': {', '.join(coincidencias_categoria[mejor_categoria])}."

    if any(termino in texto for termino in TERMINOS_PRIORIDAD_ALTA):
        prioridad_final = "alta"
        motivo_prio = "Detectado indicador de riesgo o afectación crítica."
    elif any(termino in texto for termino in TERMINOS_PRIORIDAD_MEDIA):
        prioridad_final = "media"
        motivo_prio = "Detectado fallo operativo o deterioro moderado."
    else:
        prioridad_final = "baja"
        motivo_prio = "Sin indicadores urgentes; prioridad estándar."

    return {
        "categoria": categoria_final,
        "prioridad": prioridad_final,
        "confianza": confianza,
        "motivo": f"{motivo_cat} {motivo_prio}",
    }