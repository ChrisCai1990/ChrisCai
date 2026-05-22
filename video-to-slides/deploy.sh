#!/bin/bash
# 一键部署脚本 - Ubuntu 20.04/22.04
# 用法: bash deploy.sh

set -e

APP_DIR="/opt/video-to-slides"
SERVICE_USER="www-data"

echo "=== 更新系统 ==="
apt-get update -y
apt-get install -y python3 python3-pip python3-venv nginx libgl1-mesa-glx libglib2.0-0

echo "=== 创建应用目录 ==="
mkdir -p $APP_DIR
cp -r ./* $APP_DIR/
chown -R $SERVICE_USER:$SERVICE_USER $APP_DIR

echo "=== 安装Python依赖 ==="
cd $APP_DIR
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
pip install gunicorn

echo "=== 配置systemd服务 ==="
cat > /etc/systemd/system/video-slides.service << 'EOF'
[Unit]
Description=Video to Slides Flask App
After=network.target

[Service]
User=www-data
Group=www-data
WorkingDirectory=/opt/video-to-slides
Environment="PATH=/opt/video-to-slides/venv/bin"
ExecStart=/opt/video-to-slides/venv/bin/gunicorn \
    --workers 2 \
    --timeout 300 \
    --bind 127.0.0.1:5000 \
    --max-requests 100 \
    app:app
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

echo "=== 配置Nginx ==="
cat > /etc/nginx/sites-available/video-slides << 'EOF'
server {
    listen 80;
    server_name _;

    client_max_body_size 512M;
    client_body_timeout 300s;
    proxy_read_timeout 300s;
    proxy_connect_timeout 300s;
    proxy_send_timeout 300s;

    location / {
        proxy_pass http://127.0.0.1:5000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    }
}
EOF

ln -sf /etc/nginx/sites-available/video-slides /etc/nginx/sites-enabled/
rm -f /etc/nginx/sites-enabled/default
nginx -t

echo "=== 启动服务 ==="
systemctl daemon-reload
systemctl enable video-slides
systemctl start video-slides
systemctl reload nginx

echo ""
echo "=== 部署完成 ==="
SERVER_IP=$(curl -s ifconfig.me 2>/dev/null || hostname -I | awk '{print $1}')
echo "访问地址: http://$SERVER_IP"
echo ""
echo "常用命令:"
echo "  查看状态: systemctl status video-slides"
echo "  查看日志: journalctl -u video-slides -f"
echo "  重启服务: systemctl restart video-slides"
