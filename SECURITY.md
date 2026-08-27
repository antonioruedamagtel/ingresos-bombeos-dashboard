# Política de seguridad

## Credenciales

Este repositorio no debe contener tokens ni secretos. Guarda la clave de e·sios
exclusivamente en el archivo local `.env`, que está ignorado por Git.

## Comunicación responsable

No abras una incidencia pública si detectas una credencial expuesta o una
vulnerabilidad que pueda revelar datos. Contacta de forma privada con la persona
propietaria del repositorio y facilita únicamente la información necesaria para
reproducir y corregir el problema.

Si una clave personal aparece en un commit, debe considerarse comprometida
incluso aunque el commit se elimine posteriormente. Revócala o solicita su
sustitución y elimina el secreto del historial antes de volver a publicar.
