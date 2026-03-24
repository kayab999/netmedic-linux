# 📋 NetMedic v2.0 - Roadmap de Desarrollo

Este documento rastrea el progreso de la transformación de NetMedic hacia una arquitectura profesional y mantenible.

## 🛑 FASE 0: La Purga y Normalización (Completado)
- [x] Eliminar código legacy (`netmedic_gui.py`, `netmedic.py`, `virtual_adapter.py`).
- [x] Unificar entrypoint (`python -m netmedic.app`).
- [x] Reparar instalador (`install_consolidated.sh`) eliminando rutas absolutas.
- [x] Generación automática de icono.
- [x] Actualizar README.md.

### ✅ Definition of Done (Fase 0)
- Existe un único entrypoint documentado.
- El repositorio no contiene código muerto.
- La instalación funciona en cualquier usuario sin rutas hardcodeadas.

## 🏗️ FASE 1: Arquitectura y "Safety First" (Completado)

### ✅ Definition of Done (Fase 1)
- [x] **Seguridad:** Los logs y configs tienen permisos estrictos (700/600).
- [x] **Trazabilidad:** Todos los comandos del sistema pasan por `CommandRunner` y quedan registrados.
- [x] **Robustez:** No existen llamadas a `subprocess` fuera de la capa de sistema.
- [x] **Contratos:** Cada acción define explícitamente su riesgo y reversibilidad.

### Tareas
- [x] **1.1 Infraestructura de Logging Profesional**
- [x] **1.2 Estandarización de `CommandRunner`**
- [x] **1.3 Contratos de Acción**



## 🖥️ FASE 2: UX Profesional (Completado)
- [x] **2.1 Segregación de UI**
    - [x] Crear pestañas separadas: "Repair" vs "Infrastructure".
    - [x] Mover acciones peligrosas a "Infrastructure".
- [x] **2.2 Feedback Visual**
    - [x] Implementar Spinners/Indicadores de carga reales.
    - [x] Diálogos de confirmación para acciones destructivas.

## 🚀 FASE 3: Integración VPN (Operators) (Completado)
- [x] **3.1 Esqueleto del Operador**
    - [x] Definir clase base abstracta `VPNOperator`.
    - [x] Definir `OperatorStatus` Enum.
- [x] **3.2 Implementación Angristan**
    - [x] Pin del commit para estabilidad (9c966d4).
    - [x] Gestión de estado y mutación (Index vs Script).
    - [x] Variables de entorno para modo desatendido.
- [x] **3.3 UI de Gestión**
    - [x] Crear panel modular `VPNPanel`.
    - [x] Integrar acciones asíncronas (Install, Add, Revoke).

## 📦 FASE 4: Empaquetado y Release (Completado)

### ✅ Definition of Done (Fase 4)
- [x] Existe un instalador de sistema (`install_system.sh`) que despliega en `/opt/netmedic`.
- [x] El binario es accesible globalmente como `/usr/bin/netmedic`.
- [x] El icono y .desktop se instalan en rutas estándar (`/usr/share/`).
- [x] Existe un `RELEASE_CHECKLIST.md` para validación manual.

### Tareas
- [x] **4.1 Packaging de Sistema**
    - [x] Crear `install_system.sh` (requiere root).
    - [x] Configurar despliegue en `/opt/netmedic` (venv aislado).
    - [x] Crear wrapper en `/usr/bin/netmedic`.
    - [x] Instalar assets (.desktop, icono) en `/usr/share/`.
- [x] **4.2 Checklist de Release**
    - [x] Crear documento de validación QA.

## 🔮 FASE 5: Futuro y Backlog
- [ ] **Feature: Auto-Channel Switching**
    - Implementar detección de congestión Wi-Fi.
    - Investigar integración con `upnpc` (MiniUPnPc) para negociar cambio de canal con el router.
    - Alternativa: Fuerza bruta controlada o recomendaciones inteligentes si no hay acceso UPnP.

---
**Leyenda:**
- [x] Completado
- [ ] Pendiente
- [~] En Progreso
