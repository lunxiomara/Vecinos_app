"""
Permisos de objeto para el proyecto Vecinos App — M2.
Usa django-rules para definir predicados reutilizables.

Matriz de permisos (4 roles × 8 acciones):
╔══════════════════════╦═══════════╦══════════════╦═════════╦══════════╗
║ Acción               ║ Residente ║ Administrador ║ Técnico ║ Auditor  ║
╠══════════════════════╬═══════════╬══════════════╬═════════╬══════════╣
║ ver_incidencia       ║  propia   ║      ✅       ║   ✅    ║   ✅     ║
║ crear_incidencia     ║    ✅     ║      ✅       ║   ❌    ║   ❌     ║
║ editar_incidencia    ║ pendiente ║      ✅       ║   ❌    ║   ❌     ║
║ eliminar_incidencia  ║    ❌     ║      ✅       ║   ❌    ║   ❌     ║
║ cambiar_estado       ║    ❌     ║      ✅       ║   ✅    ║   ❌     ║
║ asignar_tecnico      ║    ❌     ║      ✅       ║   ❌    ║   ❌     ║
║ ver_nota_interna     ║    ❌     ║      ✅       ║   ✅    ║   ✅     ║
║ exportar_auditar     ║    ❌     ║      ❌       ║   ❌    ║   ✅     ║
╚══════════════════════╩═══════════╩══════════════╩═════════╩══════════╝
"""

import rules


# ─────────────────────────────────────────────
# PREDICADOS BASE (bloques reutilizables)
# ─────────────────────────────────────────────

@rules.predicate
def tiene_perfil(user):
    """El usuario tiene un perfil creado."""
    return hasattr(user, 'perfil') and user.perfil is not None


@rules.predicate
def mismo_edificio(user, incidencia):
    """El usuario pertenece al mismo edificio que la incidencia."""
    if not tiene_perfil(user):
        return False
    return user.perfil.edificio_id == incidencia.edificio_id


@rules.predicate
def es_residente(user, obj=None):
    return tiene_perfil(user) and user.perfil.rol == 'residente'


@rules.predicate
def es_administrador(user, obj=None):
    return tiene_perfil(user) and user.perfil.rol == 'administrador'


@rules.predicate
def es_tecnico(user, obj=None):
    return tiene_perfil(user) and user.perfil.rol == 'tecnico'


@rules.predicate
def es_auditor(user, obj=None):
    return tiene_perfil(user) and user.perfil.rol == 'auditor'


@rules.predicate
def es_creador(user, incidencia):
    """El usuario es quien creó la incidencia."""
    return incidencia.creador_id == user.id


@rules.predicate
def incidencia_pendiente(user, incidencia):
    """La incidencia sigue en estado pendiente."""
    return incidencia.estado == 'pendiente'


# ─────────────────────────────────────────────
# PERMISOS COMPUESTOS (combinan predicados)
# ─────────────────────────────────────────────

# Ver una incidencia:
#   - Residente: solo la propia
#   - Admin / Técnico / Auditor: cualquiera del mismo edificio
rules.add_perm(
    'incidencias.ver_incidencia',
    mismo_edificio & (es_administrador | es_tecnico | es_auditor | es_creador)
)

# Crear incidencia (solo residentes y admins)
rules.add_perm(
    'incidencias.crear_incidencia',
    es_residente | es_administrador
)

# Editar incidencia:
#   - Residente: solo la propia y solo si está pendiente
#   - Admin: cualquiera del edificio
rules.add_perm(
    'incidencias.editar_incidencia',
    mismo_edificio & (es_administrador | (es_residente & es_creador & incidencia_pendiente))
)

# Eliminar incidencia: solo admin del mismo edificio
rules.add_perm(
    'incidencias.eliminar_incidencia',
    mismo_edificio & es_administrador
)

# Cambiar estado: admin o técnico del mismo edificio
rules.add_perm(
    'incidencias.cambiar_estado',
    mismo_edificio & (es_administrador | es_tecnico)
)

# Asignar técnico: solo admin del mismo edificio
rules.add_perm(
    'incidencias.asignar_tecnico',
    mismo_edificio & es_administrador
)

# Ver nota interna: admin, técnico o auditor del mismo edificio
rules.add_perm(
    'incidencias.ver_nota_interna',
    mismo_edificio & (es_administrador | es_tecnico | es_auditor)
)

# Exportar / auditar: solo auditor
rules.add_perm(
    'incidencias.exportar_auditar',
    es_auditor
)
