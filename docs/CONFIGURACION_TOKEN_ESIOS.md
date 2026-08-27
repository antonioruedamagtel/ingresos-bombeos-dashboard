# Configuración segura del token de e·sios

## Qué necesita credenciales

- **OMIE:** los ficheros públicos utilizados por la herramienta no requieren
  token, certificado ni clave API.
- **REE / e·sios:** la descarga del archivo I90 y de determinados indicadores
  utiliza una clave personal en la cabecera `x-api-key`.

## Solicitud

1. Visita la [documentación oficial de la API e·sios](https://api.esios.ree.es/).
2. Abre la opción **Personal token request**.
3. Completa el formulario indicado por Red Eléctrica.
4. Conserva la clave recibida como una credencial personal.

La interfaz y los requisitos del formulario pertenecen a REE y pueden cambiar;
la página oficial anterior es siempre la referencia válida.

## Configuración local

En Windows:

```bat
copy .env.example .env
```

Edita después `.env`:

```env
ESIOS_API_KEY=pega_aqui_tu_clave_personal
```

No añadas comillas, espacios ni el prefijo `Bearer`. La aplicación lee la clave
localmente y la envía únicamente a `api.esios.ree.es` mediante `x-api-key`.

## Uso sin token

La muestra incluida y el simulador funcionan sin credenciales. Sin token no se
puede ejecutar una actualización de e·sios, pero sí:

- abrir el dashboard;
- explorar el histórico incluido;
- ejecutar las pruebas locales;
- simular proyectos futuros sobre la serie disponible.

## Reglas de seguridad

- `.env` está ignorado por Git y nunca debe versionarse.
- No pongas el token en `README`, código, notebooks, incidencias ni capturas.
- No reutilices la clave de e·sios como credencial de OMIE.
- Si crees que la clave se ha publicado, solicita su revocación o sustitución a
  través del canal oficial de REE.
