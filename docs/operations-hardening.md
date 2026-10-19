# Exploitation Docker sécurisée

## Mot de passe PostgreSQL

`docker-compose.yml` exige désormais `POSTGRES_PASSWORD` dans `.env`. Générer un secret hexadécimal avant le premier démarrage :

```powershell
python -c "import secrets; print(secrets.token_hex(32))"
```

Copier la valeur dans `.env` sous `POSTGRES_PASSWORD`. Le format hexadécimal évite les caractères qui nécessitent un encodage dans l'URL PostgreSQL utilisée par l'application.

Pour une base déjà initialisée dans `rockib_pg_data`, changer la variable ne modifie pas le mot de passe enregistré dans PostgreSQL. Mettre à jour le rôle une seule fois avec le conteneur en marche :

```text
docker compose exec postgres psql -U rockib -d rockib_ia
ALTER ROLE rockib WITH PASSWORD '<la même valeur hexadécimale que dans .env>';
\q
docker compose up -d --force-recreate postgres app
```

Les ports PostgreSQL et Redis publiés pour le dépannage sont liés à `127.0.0.1`. Les conteneurs de l'application continuent de joindre les deux services par leur nom Docker.

## État de santé

Le healthcheck du conteneur utilise `/api/v1/health`. L'endpoint renvoie `503` quand PostgreSQL ou Redis est indisponible; Docker marque alors le service comme non prêt au lieu de se fier à la page statique servie par Nginx.
