# Checklist de Soumission - Projet DVF Pipeline

Ce document récapitule les éléments à inclure dans l'archive de soumission du projet et vérifie la conformité avec les exigences du TP.

---

## 📋 Contenu de l'archive à soumettre

### Structure de l'archive

```
projet-dvf-[nom]-[prenom].zip
│
├── README.md                          # Documentation principale
│
├── docs/
│   ├── architecture.md                # Diagramme Mermaid + explications
│   ├── tests.md                       # Rapport de tests avec commandes
│   ├── submission_checklist.md        # Ce fichier
│   └── screenshots/                   # Captures d'écran des tests
│       ├── 01_s3_buckets_list.png
│       ├── 02_lambda_functions_list.png
│       ├── 03_sqs_queues_list.png
│       ├── 04_sns_topics_list.png
│       ├── 06_bronze_bucket_content.png
│       ├── 07_bronze_lambda_logs.png
│       ├── 08_silver_bucket_content.png
│       ├── 10_silver_lambda_logs.png
│       ├── 11_gold_bucket_content.png
│       ├── 12_gold_price_m2_content.png
│       ├── 13_gold_count_by_type_content.png
│       ├── 14_gold_price_m2_logs.png
│       ├── 15_gold_count_by_type_logs.png
│       ├── 16_s3_notif_bronze.png
│       ├── 17_s3_notif_silver.png
│       ├── 18_sqs_queue_attributes.png
│       ├── 20_event_source_mappings.png
│       ├── 22_sns_publish_test.png
│       ├── 23_sns_logger_logs.png
│       ├── 24_sns_subscriptions.png
│       └── 25_cloudwatch_metrics_list.png
│
├── dvf_pipeline/
│   ├── terraform/
│   │   ├── providers.tf              # Configuration LocalStack provider
│   │   ├── s3.tf                     # Buckets Bronze/Silver/Gold
│   │   ├── lambdas.tf                # Définition des 5 Lambda Functions
│   │   ├── notifications.tf          # S3 Event Notifications
│   │   ├── sqs.tf                    # Queue SQS + DLQ
│   │   ├── sns.tf                    # Topic SNS + souscription Logger
│   │   ├── iam.tf                    # Rôles et policies IAM
│   │   ├── output.tf                 # Outputs Terraform
│   │   ├── variables.tf              # Variables Terraform
│   │   └── *.json                    # Fichiers de test (optionnels)
│   │
│   └── lambdas/
│       ├── ingest_to_bronze/
│       │   └── app.py                # Code Lambda ingestion Bronze
│       ├── bronze_to_silver/
│       │   └── app.py                # Code Lambda transformation Silver
│       ├── gold_price_m2/
│       │   └── app.py                # Code Lambda agrégation prix/m²
│       ├── gold_count_by_type/
│       │   └── app.py                # Code Lambda agrégation count by type
│       └── sns_logger/
│           └── app.py                # Code Lambda logger SNS
│
└── docker-compose.yml (optionnel)     # Configuration LocalStack
```

---

## ✅ Checklist de conformité aux exigences du TP

### 1. Infrastructure as Code (Terraform)

- [ ] **Terraform** utilisé pour toutes les ressources
- [ ] Fichiers `.tf` organisés par service (s3, lambdas, sqs, sns, iam, etc.)
- [ ] Provider LocalStack configuré avec `endpoint = "http://localhost:4566"`
- [ ] Variables Terraform documentées
- [ ] Outputs Terraform affichant ARN des ressources

---

### 2. Architecture Medallion

- [ ] **Bronze** : stockage des données brutes DVF (ZIP)
- [ ] **Silver** : transformation et nettoyage (CSV gzip, snake_case, délimiteur `;`)
- [ ] **Gold** : agrégations métier (prix/m², count by type) en JSON
- [ ] Partitionnement par année (`year=YYYY/`) pour les 3 couches

---

### 3. Event-Driven Architecture

- [ ] **S3 Event Notification** Bronze → Lambda `dvf-bronze-to-silver`
  - Prefix : `bronze/`
  - Event : `s3:ObjectCreated:*`
  
- [ ] **S3 Event Notification** Silver → SQS `dvf-silver-queue`
  - Prefix : `silver/`
  - Event : `s3:ObjectCreated:*`
  
- [ ] **SQS Queue** avec Dead Letter Queue (DLQ)
  - `MaxReceiveCount` : 5
  - `VisibilityTimeout` : 300 secondes
  
- [ ] **Event Source Mappings** SQS → Lambda Gold (2 mappings)
  - `dvf-gold-price-m2`
  - `dvf-gold-count-by-type`
  - `BatchSize` : 10

- [ ] **SNS Topic** `dvf-notifications`
  - Tous les Lambda publient des événements
  - Souscription Lambda `dvf-sns-logger`

---

### 4. Lambda Functions

- [ ] **5 Lambda Functions** créées :
  1. `dvf-ingest-to-bronze` (trigger manuel)
  2. `dvf-bronze-to-silver` (trigger S3 Notification)
  3. `dvf-gold-price-m2` (trigger SQS)
  4. `dvf-gold-count-by-type` (trigger SQS)
  5. `dvf-sns-logger` (trigger SNS)

- [ ] Runtime : Python 3.9+
- [ ] Timeouts adaptés (300s pour Bronze/Silver, 120s pour Gold)
- [ ] Rôles IAM avec permissions least-privilege
- [ ] Gestion des erreurs dans le code (try/except)

---

### 5. Observabilité

- [ ] **CloudWatch Metrics** custom publiées par chaque Lambda :
  - `ProcessingTime`
  - `RecordsProcessed`
  - `ErrorCount`
  - Namespace : `DVF/Pipeline`

- [ ] **CloudWatch Logs** pour chaque Lambda
  - Log groups automatiquement créés
  - Logs structurés avec timestamps

- [ ] **SNS Logger** capture tous les événements systèmes

---

### 6. Données DVF

- [ ] Dataset DVF traité pour **3 années** : 2023, 2024, 2025
- [ ] URLs DVF utilisées documentées dans [README.md](../README.md)
- [ ] Outputs Gold générés :
  - `gold/year=2023/avg_price_m2_2023.json`
  - `gold/year=2023/count_by_type_2023.json`
  - (idem pour 2024 et 2025)

---

### 7. Documentation

- [ ] **README.md** complet avec :
  - Vue d'ensemble du projet
  - Prérequis (Docker, Terraform, AWS CLI)
  - Instructions de démarrage LocalStack
  - Commandes Terraform (init/plan/apply)
  - Utilisation du pipeline (invocation manuelle + vérifications)
  - Section troubleshooting
  - Explications SQS et SNS
  - Sources de données DVF

- [ ] **docs/architecture.md** avec :
  - Diagramme Mermaid du pipeline complet
  - Description détaillée de chaque composant
  - Flux de données (scénarios nominal et échec)
  - Tableaux récapitulatifs

- [ ] **docs/tests.md** avec :
  - Commandes de test (PowerShell et Bash)
  - Outputs attendus pour chaque test
  - Placeholders screenshots (28 images minimum)
  - Tableau résumé des tests

- [ ] **docs/submission_checklist.md** (ce fichier)
  - Structure d'archive
  - Checklist de conformité

---

### 8. Screenshots

Vérifier que tous les screenshots suivants sont présents dans `docs/screenshots/` :

- [ ] 01_s3_buckets_list.png
- [ ] 02_lambda_functions_list.png
- [ ] 03_sqs_queues_list.png
- [ ] 04_sns_topics_list.png
- [ ] 06_bronze_bucket_content.png
- [ ] 07_bronze_lambda_logs.png
- [ ] 08_silver_bucket_content.png
- [ ] 10_silver_lambda_logs.png
- [ ] 11_gold_bucket_content.png
- [ ] 12_gold_price_m2_content.png
- [ ] 13_gold_count_by_type_content.png
- [ ] 14_gold_price_m2_logs.png
- [ ] 15_gold_count_by_type_logs.png
- [ ] 16_s3_notif_bronze.png
- [ ] 17_s3_notif_silver.png
- [ ] 18_sqs_queue_attributes.png
- [ ] 20_event_source_mappings.png
- [ ] 22_sns_publish_test.png
- [ ] 23_sns_logger_logs.png
- [ ] 24_sns_subscriptions.png
- [ ] 25_cloudwatch_metrics_list.png
- [ ] 27_dlq_messages_count.png (optionnel)

---

## 🛠️ Étapes avant la soumission

### 1. Vérification locale

**Tester le pipeline end-to-end** :

```bash
# 1. Démarrer LocalStack
docker-compose up -d

# 2. Appliquer Terraform
cd dvf_pipeline/terraform
terraform init
terraform apply -auto-approve

# 3. Déclencher l'ingestion
aws lambda invoke \
  --function-name dvf-ingest-to-bronze \
  --invocation-type Event \
  --endpoint-url http://localhost:4566 \
  --profile localstack \
  response.json

# 4. Attendre 2-3 minutes
sleep 180

# 5. Vérifier les outputs Gold
aws s3 ls s3://dvf-gold/gold/ --recursive \
  --endpoint-url http://localhost:4566 \
  --profile localstack
```

**Expected** : 6 fichiers JSON (2 par année × 3 années).

---

### 2. Captures d'écran

1. **Capturer** tous les outputs des commandes listées dans [docs/tests.md](tests.md)
2. **Renommer** les fichiers selon la convention `XX_description.png`
3. **Placer** dans `docs/screenshots/`
4. **Vérifier** que les chemins relatifs dans `tests.md` sont corrects

---

### 3. Relecture de la documentation

- [ ] Corriger les fautes d'orthographe et de grammaire
- [ ] Vérifier que tous les liens internes fonctionnent
- [ ] Vérifier la cohérence des commandes (PowerShell vs Bash)
- [ ] Tester les commandes copy-paste dans un terminal propre

---

### 4. Nettoyage du repository

**Supprimer les fichiers inutiles** :

```bash
# Fichiers temporaires
find . -name "*.pyc" -delete
find . -name "__pycache__" -delete
find . -name ".DS_Store" -delete
find . -name "response.json" -delete

# Fichiers Terraform locaux (garder .tf seulement)
rm -f dvf_pipeline/terraform/.terraform.lock.hcl
rm -rf dvf_pipeline/terraform/.terraform
rm -f dvf_pipeline/terraform/terraform.tfstate*
```

---

### 5. Création de l'archive

**PowerShell** :
```powershell
Compress-Archive -Path . -DestinationPath ../projet-dvf-[nom]-[prenom].zip
```

**Bash** :
```bash
zip -r ../projet-dvf-[nom]-[prenom].zip . \
  -x "*.git*" \
  -x "*/.terraform/*" \
  -x "*/terraform.tfstate*" \
  -x "*/__pycache__/*" \
  -x "*.pyc"
```

---

### 6. Vérification de l'archive

**Décompresser et tester** :

```bash
# Extraire
unzip projet-dvf-[nom]-[prenom].zip -d test-submission/

# Vérifier la structure
tree test-submission/ -L 3

# Tester Terraform
cd test-submission/dvf_pipeline/terraform
terraform init
terraform plan
```

---

## 📊 Critères d'évaluation (rappel)

| Critère | Points | Vérification |
|---------|--------|--------------|
| Infrastructure Terraform | 20% | Tous les `.tf` présents, syntaxe correcte |
| Architecture Medallion | 15% | 3 couches Bronze/Silver/Gold fonctionnelles |
| Event-Driven (S3, SQS, SNS) | 25% | Notifications configurées, queue avec DLQ, topic SNS |
| Lambda Functions | 20% | 5 Lambda avec code fonctionnel, timeouts adaptés |
| Observabilité (CloudWatch) | 10% | Metrics + logs + Logger SNS |
| Documentation | 10% | README + architecture.md + tests.md complets |

---

## 📝 Notes finales

### Points d'attention

1. **LocalStack** : vérifier que toutes les configurations pointent vers `http://localhost:4566`
2. **Timeouts** : s'assurer que les timeouts Lambda sont suffisants (300s min pour Bronze/Silver)
3. **URL encoding** : vérifier que les clés S3 avec caractères spéciaux sont gérées avec `urllib.parse.unquote_plus()`
4. **DLQ** : inclure un screenshot de la DLQ vide (démontre absence d'erreurs)
5. **SNS** : tester manuellement la publication SNS et vérifier les logs du Logger

---

### Livrables attendus

| Document | Statut |
|----------|--------|
| README.md | ✓ |
| docs/architecture.md | ✓ |
| docs/tests.md | ✓ |
| docs/submission_checklist.md | ✓ |
| docs/screenshots/ (22 images) | ✓ Complète |
| dvf_pipeline/terraform/*.tf | ✓ |
| dvf_pipeline/lambdas/**/app.py | ✓ |
| Archive ZIP finale | À créer |

---

### Contact

En cas de questions sur la soumission, contacter l'enseignant responsable du TP.

---

**Bon courage pour la soumission ! 🚀**

**Date** : Décembre 2025
