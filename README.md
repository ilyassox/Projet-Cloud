# Pipeline DVF - Architecture Medallion Event-Driven

## Vue d'ensemble du projet

Ce projet implémente un pipeline de données event-driven basé sur l'architecture **Medallion** (Bronze → Silver → Gold) pour le traitement du dataset **DVF (Demandes de Valeurs Foncières)**, en utilisant **LocalStack** pour simuler les services AWS et **Terraform** pour l'Infrastructure as Code.

### Architecture Medallion

- **Bronze** : données brutes (fichiers ZIP DVF téléchargés)
- **Silver** : données nettoyées et normalisées (CSV gzip avec délimiteur `;`)
- **Gold** : données agrégées et prêtes à l'analyse (JSON)

### Composants event-driven

- **S3 Notifications** : déclenchent automatiquement le traitement Bronze → Silver
- **SQS Queue** avec DLQ : découple Silver → Gold avec gestion des échecs
- **SNS Topic** : notifications centralisées avec Lambda logger
- **Lambda Functions** : traitement sans serveur à chaque étape
- **CloudWatch Metrics** : observabilité via métriques custom

Le pipeline complet traite les données DVF des années 2023, 2024 et 2025.

---

## Prérequis

### Logiciels requis

- **Docker Desktop** (version 4.x ou supérieure) - obligatoire pour LocalStack
- **Terraform** (version 1.5+)
- **AWS CLI** (version 2.x)
- **Python 3.9+** avec `pip` (pour développement Lambda optionnel)
- **Git**

### Environnement

- **Windows** : PowerShell 7+ recommandé
- **Linux/Mac** : bash ou zsh

### Configuration AWS CLI pour LocalStack

Créez ou modifiez `~/.aws/credentials` (Windows : `%USERPROFILE%\.aws\credentials`) :

```ini
[localstack]
aws_access_key_id = test
aws_secret_access_key = test
```

Créez ou modifiez `~/.aws/config` :

```ini
[profile localstack]
region = eu-west-3
output = json
```

---

## Démarrage de LocalStack

### Option 1 : Docker Compose (recommandé)

Si vous avez un fichier `docker-compose.yml` à la racine :

**PowerShell (Windows)** :
```powershell
docker-compose up -d
```

**Bash (Linux/Mac)** :
```bash
docker-compose up -d
```

### Option 2 : Docker run manuel

**PowerShell (Windows)** :
```powershell
docker run -d `
  --name localstack `
  -p 4566:4566 `
  -p 4510-4559:4510-4559 `
  -e SERVICES=s3,lambda,sqs,sns,cloudwatch,iam `
  -e DEBUG=1 `
  -e LAMBDA_EXECUTOR=docker `
  -e LAMBDA_DOCKER_NETWORK=bridge `
  -v /var/run/docker.sock:/var/run/docker.sock `
  localstack/localstack:latest
```

**Bash (Linux/Mac)** :
```bash
docker run -d \
  --name localstack \
  -p 4566:4566 \
  -p 4510-4559:4510-4559 \
  -e SERVICES=s3,lambda,sqs,sns,cloudwatch,iam \
  -e DEBUG=1 \
  -e LAMBDA_EXECUTOR=docker \
  -e LAMBDA_DOCKER_NETWORK=bridge \
  -v /var/run/docker.sock:/var/run/docker.sock \
  localstack/localstack:latest
```

### Vérification

**PowerShell** :
```powershell
curl http://localhost:4566/_localstack/health | ConvertFrom-Json
```

**Bash** :
```bash
curl http://localhost:4566/_localstack/health
```

Attendez que tous les services soient `"available"` ou `"running"`.

---

## Déploiement avec Terraform

### 1. Initialisation

Depuis le dossier `dvf_pipeline/terraform` :

**PowerShell / Bash** :
```bash
terraform init
```

### 2. Planification (optionnel)

```bash
terraform plan
```

Vérifiez les ressources à créer :
- 3 buckets S3 (dvf-bronze, dvf-silver, dvf-gold)
- 5 Lambda Functions
- 1 SQS Queue avec DLQ
- 1 SNS Topic avec souscription Lambda
- Notifications S3 et event source mappings

### 3. Application

```bash
terraform apply
```

Tapez `yes` pour confirmer.

**Durée estimée** : 2-3 minutes.

### 4. Outputs

Terraform affiche les ARN et noms des ressources créées :
- Buckets S3
- Lambda Functions ARN
- SQS Queue URL
- SNS Topic ARN

---

## Utilisation du pipeline

### Étape 1 : Ingestion Bronze (déclenchement manuel)

Le Lambda `dvf-ingest-to-bronze` télécharge les fichiers DVF ZIP et les stocke dans `s3://dvf-bronze/bronze/year=YYYY/`.

**PowerShell** :
```powershell
aws lambda invoke `
  --function-name dvf-ingest-to-bronze `
  --invocation-type Event `
  --endpoint-url http://localhost:4566 `
  --profile localstack `
  --region eu-west-3 `
  response.json
```

**Bash** :
```bash
aws lambda invoke \
  --function-name dvf-ingest-to-bronze \
  --invocation-type Event \
  --endpoint-url http://localhost:4566 \
  --profile localstack \
  --region eu-west-3 \
  response.json
```

**Vérification Bronze** :

**PowerShell** :
```powershell
aws s3 ls s3://dvf-bronze/bronze/ `
  --recursive `
  --endpoint-url http://localhost:4566 `
  --profile localstack
```

**Bash** :
```bash
aws s3 ls s3://dvf-bronze/bronze/ \
  --recursive \
  --endpoint-url http://localhost:4566 \
  --profile localstack
```

**Expected** : fichiers ZIP dans `bronze/year=2023/`, `bronze/year=2024/`, `bronze/year=2025/`.

---

### Étape 2 : Traitement Silver (automatique via S3 Notification)

Le dépôt d'un fichier dans `s3://dvf-bronze/bronze/` déclenche automatiquement le Lambda `dvf-bronze-to-silver` qui :
1. Décompresse le ZIP
2. Normalise les colonnes en snake_case
3. Nettoie les types de données
4. Écrit un CSV gzip avec délimiteur `;` dans `s3://dvf-silver/silver/year=YYYY/`

**Vérification Silver** :

**PowerShell** :
```powershell
aws s3 ls s3://dvf-silver/silver/ `
  --recursive `
  --endpoint-url http://localhost:4566 `
  --profile localstack
```

**Bash** :
```bash
aws s3 ls s3://dvf-silver/silver/ \
  --recursive \
  --endpoint-url http://localhost:4566 \
  --profile localstack
```

**Expected** : fichiers `.csv.gz` dans `silver/year=2023/`, `silver/year=2024/`, `silver/year=2025/`.

---

### Étape 3 : Traitement Gold (automatique via SQS)

Le dépôt d'un fichier dans `s3://dvf-silver/silver/` envoie un message vers la queue SQS `dvf-silver-queue`.

Deux Lambda Functions sont déclenchées par event source mapping :

1. **dvf-gold-price-m2** : calcule le prix moyen au m² par année
   - Output : `s3://dvf-gold/gold/year=YYYY/avg_price_m2_YYYY.json`

2. **dvf-gold-count-by-type** : compte le nombre de propriétés vendues par type/ville/année
   - Output : `s3://dvf-gold/gold/year=YYYY/count_by_type_YYYY.json`

**Vérification Gold** :

**PowerShell** :
```powershell
aws s3 ls s3://dvf-gold/gold/ `
  --recursive `
  --endpoint-url http://localhost:4566 `
  --profile localstack
```

**Bash** :
```bash
aws s3 ls s3://dvf-gold/gold/ \
  --recursive \
  --endpoint-url http://localhost:4566 \
  --profile localstack
```

**Expected** : fichiers JSON dans `gold/year=2023/`, `gold/year=2024/`, `gold/year=2025/`.

---

## Vérification des composants event-driven

### S3 Notifications

**Configuration Bronze → Silver** :

**PowerShell / Bash** :
```bash
aws s3api get-bucket-notification-configuration \
  --bucket dvf-bronze \
  --endpoint-url http://localhost:4566 \
  --profile localstack
```

**Expected** : LambdaFunctionConfiguration avec `Filter.Key.FilterRules.Prefix = "bronze/"`.

**Configuration Silver → SQS** :

```bash
aws s3api get-bucket-notification-configuration \
  --bucket dvf-silver \
  --endpoint-url http://localhost:4566 \
  --profile localstack
```

**Expected** : QueueConfiguration avec `Filter.Key.FilterRules.Prefix = "silver/"`.

---

### SQS Queue et DLQ

**Liste des queues** :

**PowerShell / Bash** :
```bash
aws sqs list-queues \
  --endpoint-url http://localhost:4566 \
  --profile localstack
```

**Expected** : `dvf-silver-queue` et `dvf-silver-dlq`.

**Attributs de la queue** :

```bash
aws sqs get-queue-attributes \
  --queue-url http://localhost:4566/000000000000/dvf-silver-queue \
  --attribute-names All \
  --endpoint-url http://localhost:4566 \
  --profile localstack
```

**Expected** : `RedrivePolicy` pointant vers la DLQ.

---

### Event Source Mappings (SQS → Lambda)

**PowerShell / Bash** :
```bash
aws lambda list-event-source-mappings \
  --endpoint-url http://localhost:4566 \
  --profile localstack
```

**Expected** : 2 mappings pour `dvf-gold-price-m2` et `dvf-gold-count-by-type` avec source `dvf-silver-queue`.

---

### SNS Topic et Logger Lambda

**Liste des topics** :

```bash
aws sns list-topics \
  --endpoint-url http://localhost:4566 \
  --profile localstack
```

**Expected** : topic `dvf-notifications`.

**Test de publication SNS** :

**PowerShell** :
```powershell
aws sns publish `
  --topic-arn arn:aws:sns:eu-west-3:000000000000:dvf-notifications `
  --message "Test notification from README" `
  --endpoint-url http://localhost:4566 `
  --profile localstack
```

**Bash** :
```bash
aws sns publish \
  --topic-arn arn:aws:sns:eu-west-3:000000000000:dvf-notifications \
  --message "Test notification from README" \
  --endpoint-url http://localhost:4566 \
  --profile localstack
```

**Vérification logs** :

```bash
aws logs tail /aws/lambda/dvf-sns-logger \
  --follow \
  --endpoint-url http://localhost:4566 \
  --profile localstack
```

**Expected** : message "Test notification from README" dans les logs.

---

## CloudWatch Metrics

Chaque Lambda publie des métriques custom via `put_metric_data` :
- Namespace : `DVF/Pipeline`
- Métriques : `ProcessingTime`, `RecordsProcessed`, `ErrorCount`

**Liste des métriques** :

```bash
aws cloudwatch list-metrics \
  --namespace DVF/Pipeline \
  --endpoint-url http://localhost:4566 \
  --profile localstack
```

---

## Architectures event-driven

### Pourquoi SQS entre Silver et Gold ?

1. **Découplage** : les Lambda Gold ne sont pas bloquants pour la couche Silver
2. **Résilience** : retry automatique (jusqu'à 5x par défaut)
3. **Dead Letter Queue** : capture les messages en échec pour analyse
4. **Scaling** : plusieurs Lambda peuvent consommer en parallèle
5. **Backpressure** : la queue absorbe les pics de charge

### Pourquoi SNS pour les notifications ?

1. **Fan-out** : un événement peut notifier plusieurs subscribers
2. **Centralisation** : point unique pour toutes les notifications système
3. **Flexibilité** : ajout facile de nouveaux subscribers (email, Slack, etc.)
4. **Observabilité** : le Logger Lambda capture tous les événements importants

---

## Sources de données

Le dataset DVF provient du portail open data du gouvernement français :

- **2023** : [https://files.data.gouv.fr/geo-dvf/latest/csv/2023/full.csv.gz](https://files.data.gouv.fr/geo-dvf/latest/csv/2023/full.csv.gz)
- **2024** : [https://files.data.gouv.fr/geo-dvf/latest/csv/2024/full.csv.gz](https://files.data.gouv.fr/geo-dvf/latest/csv/2024/full.csv.gz)
- **2025** : [https://files.data.gouv.fr/geo-dvf/latest/csv/2025/full.csv.gz](https://files.data.gouv.fr/geo-dvf/latest/csv/2025/full.csv.gz)

**Note** : les URLs peuvent varier selon la disponibilité des données.

---

## Troubleshooting

### Erreur : "Cannot connect to LocalStack"

**Symptôme** : `Could not connect to the endpoint URL: "http://localhost:4566/"`

**Solution** :
1. Vérifier que Docker Desktop est démarré
2. Vérifier que le container LocalStack est running : `docker ps`
3. Redémarrer LocalStack : `docker restart localstack`

---

### Erreur : Lambda timeout

**Symptôme** : Lambda timeout après 3 secondes

**Cause** : timeout trop court pour télécharger/traiter les fichiers DVF

**Solution** : augmenter le timeout dans [lambdas.tf](dvf_pipeline/terraform/lambdas.tf) :
```hcl
timeout = 300  # 5 minutes
```

Puis :
```bash
terraform apply
```

---

### Erreur : "NoSuchKey" avec caractères spéciaux

**Symptôme** : Erreur S3 `NoSuchKey` lors de la lecture d'objets avec espaces ou caractères spéciaux

**Cause** : URL encoding incorrect

**Solution** : dans le code Lambda, utiliser `urllib.parse.unquote_plus()` :
```python
import urllib.parse

key = urllib.parse.unquote_plus(event['Records'][0]['s3']['object']['key'])
```

---

### Erreur : "No space left on device" (LocalStack)

**Symptôme** : erreur lors du téléchargement de fichiers volumineux

**Cause** : espace Docker insuffisant

**Solution** :
1. Nettoyer les images/containers inutilisés : `docker system prune -a`
2. Augmenter l'espace disque alloué à Docker Desktop (Settings → Resources)

---

### Erreur : Event source mapping inactif

**Symptôme** : Lambda Gold ne se déclenche pas malgré les messages dans SQS

**Vérification** :
```bash
aws lambda list-event-source-mappings \
  --endpoint-url http://localhost:4566 \
  --profile localstack
```

**Solution** : vérifier l'état (`State`) doit être `Enabled`. Si `Disabled`, recréer avec Terraform :
```bash
terraform destroy -target=aws_lambda_event_source_mapping.gold_price_m2
terraform apply
```

---

### Logs CloudWatch vides

**Symptôme** : `aws logs tail` ne retourne rien

**Cause** : LocalStack ne crée pas toujours les log groups automatiquement

**Solution** : déclencher le Lambda une fois, puis réessayer. Ou créer manuellement :
```bash
aws logs create-log-group \
  --log-group-name /aws/lambda/dvf-ingest-to-bronze \
  --endpoint-url http://localhost:4566 \
  --profile localstack
```

---

## Nettoyage

### Détruire l'infrastructure

```bash
cd dvf_pipeline/terraform
terraform destroy
```

### Arrêter LocalStack

```bash
docker stop localstack
docker rm localstack
```

---

## Documentation supplémentaire

- [Architecture détaillée](docs/architecture.md) : diagramme Mermaid complet
- [Rapport de tests](docs/tests.md) : commandes et screenshots
- [Checklist de soumission](docs/submission_checklist.md) : structure de l'archive

---

## Auteur

Projet réalisé dans le cadre du TP Cloud Computing.

**Date** : Décembre 2025
