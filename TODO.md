# TODO: NetMedic v1.0.0 Release Roadmap

## [ ] Fase 1: Limpieza y Documentación
- [x] Configuración de .gitignore
- [x] Inicialización de CHANGELOG.md
- [x] Aplicación de Licencia MIT
- [ ] Revisión final de comentarios de depuración en el código fuente

## [ ] Fase 2: Empaquetado y Distribución
- [x] Configuración de pyproject.toml con dependencias opcionales
- [ ] Creación de `build_standalone.sh` (PyInstaller)
- [ ] Creación de `build_ai.sh` (PyInstaller + IA)
- [ ] Verificación de generación de binarios en `/dist`

## [ ] Fase 3: Pruebas de Integración Final
- [ ] Test de instalación limpia: `pip install .[ai]`
- [ ] Validación de Aceleración por Hardware (Vulkan/CUDA)
- [ ] Verificación de persistencia de recursos en reinicios
- [ ] Prueba de estrés del bus IPC (Socket UNIX)

## [ ] Fase 4: Lanzamiento Oficial
- [ ] Commit final y Tag `v1.0.0`
- [ ] Generación de Assets de Release en GitHub
- [ ] Publicación de Notas de Versión
