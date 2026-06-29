#!/usr/bin/env bash
set -e

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV="$REPO_DIR/.venv"
SYSTEMD_DIR="$HOME/.config/systemd/user"
ENV_FILE="$HOME/.config/flashcard-pipeline/env"
DATA_DIR="$HOME/.local/share/flashcard-pipeline"

echo "=== Flashcard Pipeline — Installation ==="
echo "Répertoire : $REPO_DIR"
echo ""

# 1. Venv + dépendances
echo "[1/5] Création du venv et installation des dépendances..."
python3 -m venv "$VENV"
"$VENV/bin/pip" install -q -r "$REPO_DIR/requirements.txt"
echo "      OK"

# 2. Dossiers de données
echo "[2/5] Création des dossiers de données..."
mkdir -p "$DATA_DIR"
mkdir -p "$HOME/.config/flashcard-pipeline"
echo "      OK"

# 3. Clé API
echo "[3/5] Configuration de la clé API Infercom..."
if [ ! -f "$ENV_FILE" ]; then
    echo "INFERCOM_API_KEY=your-key-here" > "$ENV_FILE"
    chmod 600 "$ENV_FILE"
    echo "      → Fichier créé : $ENV_FILE"
    echo "      ⚠  Remplis ta clé API avant de lancer le pipeline."
else
    echo "      → $ENV_FILE existe déjà, non modifié."
fi

# 4. Systemd (génération dynamique avec le bon chemin)
echo "[4/5] Installation du service systemd..."
mkdir -p "$SYSTEMD_DIR"

cat > "$SYSTEMD_DIR/flashcard-pipeline.service" << EOF
[Unit]
Description=Flashcard Pipeline — génération Anki depuis les cours
After=network.target

[Service]
Type=oneshot
WorkingDirectory=$REPO_DIR
ExecStart=$VENV/bin/python3 $REPO_DIR/pipeline.py
EnvironmentFile=$ENV_FILE
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=default.target
EOF

cat > "$SYSTEMD_DIR/flashcard-pipeline.timer" << EOF
[Unit]
Description=Lance le pipeline flashcard toutes les heures
Requires=flashcard-pipeline.service

[Timer]
OnBootSec=5min
OnUnitActiveSec=1h
Unit=flashcard-pipeline.service

[Install]
WantedBy=timers.target
EOF

systemctl --user daemon-reload
systemctl --user enable --now flashcard-pipeline.timer
echo "      OK — timer actif toutes les heures"

# 5. Rappels config
echo ""
echo "[5/5] Checklist finale :"
echo ""
echo "  1. Édite config.yaml et renseigne tes chemins Syncthing :"
echo "       input_dir  : dossier où tu déposes tes cours (PDF, PPTX…)"
echo "       output_dir : dossier synchronisé avec AnkiDroid"
echo ""
echo "  2. Mets ta clé Infercom dans :"
echo "       $ENV_FILE"
echo ""
echo "  3. Test manuel :"
echo "       $VENV/bin/python3 $REPO_DIR/pipeline.py"
echo ""
echo "  4. Logs :"
echo "       journalctl --user -u flashcard-pipeline.service -f"
echo ""
echo "=== Installation terminée ==="
