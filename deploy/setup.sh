#!/bin/bash
set -e

INSTALL_DIR="/opt/aistock"
REPO_URL="https://github.com/jya1park/AgentforAIStock.git"

echo "=== AI Stock 서버 셋업 시작 ==="

# 1. 시스템 패키지
echo "[1/7] 시스템 패키지 설치..."
sudo apt update -qq
sudo apt install -y -qq python3 python3-pip python3-venv git fonts-nanum

# 2. 타임존 KST
echo "[2/7] 타임존 Asia/Seoul 설정..."
sudo timedatectl set-timezone Asia/Seoul

# 3. 프로젝트 클론
if [ ! -d "$INSTALL_DIR/.git" ]; then
    echo "[3/7] 프로젝트 클론..."
    sudo mkdir -p "$INSTALL_DIR"
    sudo chown "$USER:$USER" "$INSTALL_DIR"
    git clone "$REPO_URL" "$INSTALL_DIR"
else
    echo "[3/7] 프로젝트 업데이트 (git pull)..."
    cd "$INSTALL_DIR" && git pull
fi

cd "$INSTALL_DIR"

# 4. Python 가상환경 + 의존성
echo "[4/7] Python 가상환경 + 의존성 설치..."
python3 -m venv venv
./venv/bin/pip install --upgrade pip -q
./venv/bin/pip install -r requirements.txt -q

# 5. .env 파일
if [ ! -f .env ]; then
    echo "[5/7] .env 파일 생성 (API 키 입력 필요)..."
    cat > .env <<'ENVEOF'
OPENAI_API_KEY=여기에_OpenAI_키
ANTHROPIC_API_KEY=여기에_Anthropic_키
TELEGRAM_BOT_TOKEN=여기에_텔레그램_봇_토큰
TELEGRAM_CHAT_ID=여기에_텔레그램_채팅_ID
ENVEOF
    echo ""
    echo "  >>> .env 파일 편집 필요: nano $INSTALL_DIR/.env"
    echo "  >>> 4개 키를 모두 입력한 후 이 스크립트를 다시 실행하세요."
    echo ""
    exit 0
else
    echo "[5/7] .env 파일 확인됨"
fi

# 6. 로그 디렉토리
mkdir -p logs

# 7. systemd 서비스 (봇 상시 가동)
echo "[6/7] systemd 서비스 등록..."
sudo cp deploy/aistock-bot.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable aistock-bot
sudo systemctl restart aistock-bot

# 8. crontab (morning/evening)
echo "[7/7] crontab 등록..."
(crontab -l 2>/dev/null | grep -v "src.main morning" | grep -v "src.main evening"; cat deploy/crontab.txt) | crontab -

echo ""
echo "=== 설치 완료 ==="
echo ""
echo "  봇 상태 확인:  sudo systemctl status aistock-bot"
echo "  봇 로그 확인:  sudo journalctl -u aistock-bot -f"
echo "  morning 로그:  tail -f $INSTALL_DIR/logs/morning.log"
echo "  .env 편집:     nano $INSTALL_DIR/.env"
echo "  수동 테스트:    cd $INSTALL_DIR && ./venv/bin/python -m src.main morning"
echo ""
echo "  cron 스케줄: 평일 08:00 morning / 18:00 evening (KST)"
echo "  봇: 24/7 상시 가동 (VM 재부팅 시 자동 시작)"
echo ""
