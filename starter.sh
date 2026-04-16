#!/bin/bash
# PlotPilot 启动菜单
# 墨枢 - AI 驱动的长篇小说创作平台

export PYTHONIOENCODING="utf-8"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

ensure_uv() {
    if command -v uv &> /dev/null; then
        echo -e "\033[32muv 已安装: $(uv --version)\033[0m"
        return 0
    fi
    
    echo -e "\033[33m未检测到 uv，正在安装...\033[0m"
    
    if command -v curl &> /dev/null; then
        curl -LsSf https://astral.sh/uv/install.sh | sh
        if [ $? -eq 0 ]; then
            export PATH="$HOME/.local/bin:$PATH"
            if command -v uv &> /dev/null; then
                echo -e "\033[32muv 安装成功: $(uv --version)\033[0m"
                return 0
            fi
        fi
    fi
    
    echo -e "\033[33m官方安装脚本失败，尝试使用 pip 安装...\033[0m"
    if command -v pip3 &> /dev/null; then
        pip3 install uv
    elif command -v pip &> /dev/null; then
        pip install uv
    else
        echo -e "\033[31m无法安装 uv，请手动安装: curl -LsSf https://astral.sh/uv/install.sh | sh\033[0m"
        return 1
    fi
    
    if command -v uv &> /dev/null; then
        echo -e "\033[32muv 安装成功: $(uv --version)\033[0m"
        return 0
    fi
    
    return 1
}

free_port() {
    local port=$1
    echo -e "\033[36m检查端口 $port 占用情况...\033[0m"

    if command -v lsof &> /dev/null; then
        local pids=$(lsof -ti:$port 2>/dev/null)
        if [ -n "$pids" ]; then
            for pid in $pids; do
                local proc_name=$(ps -p "$pid" -o comm= 2>/dev/null)
                if [ -n "$proc_name" ]; then
                    echo -e "\033[33m发现进程占用端口 $port : PID=$pid, Name=$proc_name\033[0m"
                    read -p "是否终止该进程？ [y/N]: " confirm
                    if [[ "$confirm" =~ ^[Yy]$ ]]; then
                        kill -9 "$pid" 2>/dev/null
                        echo -e "\033[32m已终止进程 PID=$pid\033[0m"
                    else
                        echo -e "\033[33m跳过终止进程\033[0m"
                    fi
                fi
            done
            sleep 0.5
        else
            echo -e "\033[32m端口 $port 未被占用\033[0m"
        fi
    elif command -v netstat &> /dev/null; then
        local connections=$(netstat -tln 2>/dev/null | grep ":$port ")
        if [ -n "$connections" ]; then
            echo -e "\033[33m发现端口 $port 被占用\033[0m"
            local pids=$(netstat -tlnp 2>/dev/null | grep ":$port " | sed -n 's/.*pid=\([0-9]*\).*/\1/p')
            for pid in $pids; do
                if [ -n "$pid" ]; then
                    read -p "是否终止占用端口 $port 的进程 (PID=$pid)？ [y/N]: " confirm
                    if [[ "$confirm" =~ ^[Yy]$ ]]; then
                        kill -9 "$pid" 2>/dev/null
                        echo -e "\033[32m已终止进程 PID=$pid\033[0m"
                    else
                        echo -e "\033[33m跳过终止进程\033[0m"
                    fi
                fi
            done
            sleep 0.5
        else
            echo -e "\033[32m端口 $port 未被占用\033[0m"
        fi
    else
        echo -e "\033[33m未找到 lsof 或 netstat，无法检查端口占用\033[0m"
    fi
}

show_menu() {
    clear
    echo -e "\033[36m========================================\033[0m"
    echo -e "\033[36m  PlotPilot (墨枢) 启动菜单\033[0m"
    echo -e "\033[36m========================================\033[0m"
    echo ""
    echo -e "\033[33m1.\033[0m 启动双端服务（后端+前端）"
    echo -e "\033[33m2.\033[0m 启动后端服务"
    echo -e "\033[33m3.\033[0m 启动前端开发服务器"
    echo -e "\033[33m4.\033[0m Docker 启动 Qdrant 向量数据库"
    echo -e "\033[33m5.\033[0m 运行测试"
    echo -e "\033[33m6.\033[0m 懒人安装（一键配置环境）"
    echo -e "\033[31m0.\033[0m 退出"
    echo ""
    echo -e "\033[36m========================================\033[0m"
}

ask_reinstall() {
    local dir_name=$1
    local dir_path=$2
    echo -e "\033[33m检测到已存在的 $dir_name: $dir_path\033[0m"
    echo -e "\033[33m请选择操作:\033[0m"
    echo -e "  \033[36m不选则跳过\033[0m) 保留现有目录"
    echo -e "  \033[36m9\033[0m) 删除并重建"
    read -p "请选择 [跳过/9]: " choice
    case $choice in
        9)
            echo -e "\033[33m正在删除 $dir_path...\033[0m"
            rm -rf "$dir_path"
            return 0
            ;;
        *)  
            echo -e "\033[32m跳过 $dir_name 安装\033[0m"
            return 1
            ;;
    esac
}

check_backend_ready() {
    local max_attempts=30
    local attempt=1
    echo -e "\033[36m正在检测后端服务启动状态...\033[0m"
    
    while [ $attempt -le $max_attempts ]; do
        if curl -s http://127.0.0.1:8005/docs > /dev/null 2>&1 || curl -s http://127.0.0.1:8005/ > /dev/null 2>&1; then
            echo -e "\033[32m后端服务已就绪！\033[0m"
            return 0
        fi
        echo -e "\033[33m等待后端服务启动... ($attempt/$max_attempts)\033[0m"
        sleep 2
        attempt=$((attempt + 1))
    done
    
    echo -e "\033[31m后端服务启动超时，请检查后端日志: backend.log\033[0m"
    return 1
}

start_both() {
    echo -e "\n\033[32m正在启动双端服务（后端+前端）...\033[0m"

    # 咨询是否启动 Qdrant
    echo -e "\n\033[36m[0/2] 向量数据库配置...\033[0m"
    echo -e "\033[33mQdrant 向量数据库用于语义检索功能，是否启动？ [y/N]: \033[0m"
    read -r start_qdrant
    
    if [[ "$start_qdrant" == "y" || "$start_qdrant" == "Y" ]]; then
        echo -e "\033[33m正在启动 Qdrant 向量数据库...\033[0m"
        if ! start_qdrant; then
            echo -e "\033[31mQdrant 启动失败，但将继续启动其他服务\033[0m"
        fi
        sleep 2
    else
        echo -e "\033[32m跳过 Qdrant 启动\033[0m"
    fi

    echo -e "\n\033[36m[1/2] 启动后端服务...\033[0m"
    free_port 8005

    if ! ensure_uv; then
        echo -e "\033[31muv 安装失败，无法继续\033[0m"
        return
    fi

    VENV_PATH="$SCRIPT_DIR/.venv"
    if [ -d "$VENV_PATH" ]; then
        echo -e "\033[36m检测到虚拟环境，正在激活...\033[0m"
        source "$VENV_PATH/bin/activate" 2>/dev/null
    fi

    if ! command -v uvicorn &> /dev/null;
    then
        echo -e "\033[31m未找到 uvicorn，请先安装依赖: uv pip install -r requirements.txt\033[0m"
        return
    fi

    echo -e "\033[32m后端服务启动中 (http://localhost:8005)...\033[0m"
    cd "$SCRIPT_DIR"
    nohup uvicorn interfaces.main:app --host 0.0.0.0 --port 8005 --reload > backend.log 2>&1 &
    BACKEND_PID=$!
    echo -e "\033[36m后端服务 PID: $BACKEND_PID\033[0m"

    echo -e "\n\033[36m[2/2] 启动前端开发服务器...\033[0m"
    free_port 3000

    FRONTEND_DIR="$SCRIPT_DIR/frontend"
    if [ ! -d "$FRONTEND_DIR" ]; then
        echo -e "\033[31m前端目录不存在: $FRONTEND_DIR\033[0m"
        kill $BACKEND_PID 2>/dev/null
        return
    fi

    cd "$FRONTEND_DIR"

    if [ ! -d "node_modules" ]; then
        echo -e "\033[33m未找到 node_modules，正在安装依赖...\033[0m"
        npm install
        if [ $? -ne 0 ]; then
            echo -e "\033[31m前端依赖安装失败\033[0m"
            kill $BACKEND_PID 2>/dev/null
            cd "$SCRIPT_DIR"
            return
        fi
    fi

    if ! check_backend_ready; then
        echo -e "\033[31m后端服务未就绪，是否继续启动前端？ [y/N]: \033[0m"
        read -r continue_frontend
        if [[ ! "$continue_frontend" =~ ^[Yy]$ ]]; then
            kill $BACKEND_PID 2>/dev/null
            cd "$SCRIPT_DIR"
            return
        fi
    fi

    echo -e "\033[32m前端开发服务器启动中...\033[0m"
    echo -e "\033[37m按 Ctrl+C 停止前端服务\033[0m"
    echo ""
    echo -e "\033[32m后端服务运行在: http://localhost:8005\033[0m"
    echo -e "\033[32m前端服务运行在: http://localhost:3000\033[0m"
    if [[ "$start_qdrant" == "y" || "$start_qdrant" == "Y" ]]; then
        echo -e "\033[32mQdrant 运行在: http://localhost:6333\033[0m"
    fi
    echo ""
    echo -e "\033[33m提示: 后端服务已在后台运行，前端服务结束后不会自动停止后端服务\033[0m"
    echo -e "\033[33m如需停止后端服务，请手动执行: kill $BACKEND_PID\033[0m"
    echo ""

    npm run dev

    cd "$SCRIPT_DIR"
}

start_backend() {
    echo -e "\n\033[32m正在启动后端服务...\033[0m"

    free_port 8005

    if ! ensure_uv; then
        echo -e "\033[31muv 安装失败，无法继续\033[0m"
        return
    fi

    VENV_PATH="$SCRIPT_DIR/.venv"
    if [ -d "$VENV_PATH" ]; then
        echo -e "\033[36m检测到虚拟环境，正在激活...\033[0m"
        source "$VENV_PATH/bin/activate" 2>/dev/null
    fi

    if ! command -v uvicorn &> /dev/null;
    then
        echo -e "\033[31m未找到 uvicorn，请先安装依赖: uv pip install -r requirements.txt\033[0m"
        return
    fi

    echo -e "\033[32m后端服务启动中 (http://localhost:8005)...\033[0m"
    echo -e "\033[37m按 Ctrl+C 停止服务\033[0m"
    echo ""

    cd "$SCRIPT_DIR"
    uvicorn interfaces.main:app --host 127.0.0.1 --port 8005 --reload
}

start_frontend() {
    echo -e "\n\033[32m正在启动前端开发服务器...\033[0m"

    free_port 3000

    FRONTEND_DIR="$SCRIPT_DIR/frontend"
    if [ ! -d "$FRONTEND_DIR" ]; then
        echo -e "\033[31m前端目录不存在: $FRONTEND_DIR\033[0m"
        return
    fi

    cd "$FRONTEND_DIR"

    if [ ! -d "node_modules" ]; then
        echo -e "\033[33m未找到 node_modules，正在安装依赖...\033[0m"
        npm install
        if [ $? -ne 0 ]; then
            echo -e "\033[31m依赖安装失败\033[0m"
            cd "$SCRIPT_DIR"
            return
        fi
    fi

    echo -e "\033[32m前端开发服务器启动中...\033[0m"
    echo -e "\033[37m按 Ctrl+C 停止服务\033[0m"
    echo ""
    echo -e "\033[32m前端服务运行在: http://localhost:3000\033[0m"
    echo ""

    npm run dev

    cd "$SCRIPT_DIR"
}

run_tests() {
    echo -e "\n\033[32m正在运行测试...\033[0m"

    TESTS_DIR="$SCRIPT_DIR/tests"
    if [ ! -d "$TESTS_DIR" ]; then
        echo -e "\033[33mtests 目录不存在: $TESTS_DIR\033[0m"
        echo -e "\033[36m正在检查是否有其他测试文件...\033[0m"

        if command -v pytest &> /dev/null; then
            echo -e "\033[32m检测到 pytest，尝试运行测试...\033[0m"
            pytest -v
        else
            echo -e "\033[31m未找到 pytest，请先安装: uv pip install pytest\033[0m"
        fi
        return
    fi

    VENV_PATH="$SCRIPT_DIR/.venv"
    if [ -d "$VENV_PATH" ]; then
        source "$VENV_PATH/bin/activate" 2>/dev/null
    fi

    echo -e "\033[32m运行单元测试和集成测试...\033[0m"
    pytest tests/unit/ tests/integration/ -v
}

start_qdrant() {
    echo -e "\n\033[32m启动 Qdrant 向量数据库...\033[0m"

    local docker_cmd=""

    if command -v docker &> /dev/null; then
        if docker info &> /dev/null; then
            docker_cmd="docker"
        elif sudo docker info &> /dev/null; then
            docker_cmd="sudo docker"
        else
            echo -e "\033[31m无法访问 Docker，请检查 Docker 安装和权限配置\033[0m"
            echo -e "\033[33m提示: 可尝试 'sudo usermod -aG docker $USER' 添加用户到 docker 组\033[0m"
            return 1
        fi
    else
        echo -e "\033[33m未找到 Docker，正在安装...\033[0m"
        if command -v apt-get &> /dev/null; then
            sudo apt-get update
            sudo apt-get install -y docker.io docker-compose
        elif command -v brew &> /dev/null; then
            brew install docker docker-compose
        elif command -v pacman &> /dev/null; then
            sudo pacman -S docker docker-compose
        else
            echo -e "\033[31m无法自动安装 Docker，请手动安装\033[0m"
            return 1
        fi

        if sudo docker info &> /dev/null; then
            docker_cmd="sudo docker"
        else
            echo -e "\033[31mDocker 安装后仍无法访问，请检查权限\033[0m"
            return 1
        fi
    fi

    echo -e "\033[36m检查 Docker 服务状态...\033[0m"
    if ! $docker_cmd info &> /dev/null; then
        echo -e "\033[33mDocker 服务未启动，正在尝试启动...\033[0m"

        if command -v systemctl &> /dev/null; then
            echo -e "\033[33m使用 systemctl 启动 Docker 服务...\033[0m"
            sudo systemctl start docker
        elif command -v service &> /dev/null; then
            echo -e "\033[33m使用 service 启动 Docker 服务...\033[0m"
            sudo service docker start
        else
            echo -e "\033[31m无法自动启动 Docker 服务，请手动启动\033[0m"
            echo -e "\033[33m提示: 请运行 'sudo systemctl start docker' 或 'sudo service docker start' 启动 Docker 服务\033[0m"
            return 1
        fi

        sleep 3

        if ! $docker_cmd info &> /dev/null; then
            echo -e "\033[31mDocker 服务启动失败，请手动启动\033[0m"
            return 1
        fi
    fi

    if [ -f "$SCRIPT_DIR/docker-compose.yml" ]; then
        echo -e "\033[32m正在启动 Qdrant...\033[0m"
        $docker_cmd compose up -d
        if [ $? -eq 0 ]; then
            echo -e "\033[32mQdrant 已启动，运行在 http://localhost:6333\033[0m"
        else
            echo -e "\033[31mQdrant 启动失败，请检查 Docker 日志\033[0m"
            return 1
        fi
    else
        echo -e "\033[33mdocker-compose.yml 文件不存在，跳过启动 Qdrant\033[0m"
    fi
}

lazy_install() {
    echo -e "\n\033[35m========================================\033[0m"
    echo -e "\033[35m  懒人安装 - 一键配置环境\033[0m"
    echo -e "\033[35m========================================\033[0m"

    cd "$SCRIPT_DIR"
    echo -e "\033[36m[1/7] 锁定项目根目录: $SCRIPT_DIR\033[0m"

    echo -e "\n\033[36m[2/7] 检测并安装 uv...\033[0m"
    if ! ensure_uv; then
        echo -e "\033[31muv 安装失败，无法继续\033[0m"
        return 1
    fi

    echo -e "\n\033[36m[3/7] 创建虚拟环境...\033[0m"
    VENV_PATH="$SCRIPT_DIR/.venv"
    if [ -d "$VENV_PATH" ]; then
        if ! ask_reinstall "虚拟环境" "$VENV_PATH"; then
            echo -e "\033[32m使用现有的虚拟环境\033[0m"
        else
            echo -e "\033[33m正在使用 uv 创建虚拟环境...\033[0m"
            uv venv --clear "$VENV_PATH"
            if [ $? -ne 0 ]; then
                echo -e "\033[31m创建虚拟环境失败，但将继续执行后续步骤\033[0m"
            else
                echo -e "\033[32m虚拟环境创建成功\033[0m"
            fi
        fi
    else
        echo -e "\033[33m正在使用 uv 创建虚拟环境...\033[0m"
        uv venv "$VENV_PATH"
        if [ $? -ne 0 ]; then
            echo -e "\033[31m创建虚拟环境失败，但将继续执行后续步骤\033[0m"
        else
            echo -e "\033[32m虚拟环境创建成功\033[0m"
        fi
    fi

    echo -e "\033[36m激活虚拟环境...\033[0m"
    source "$VENV_PATH/bin/activate" 2>/dev/null

    echo -e "\n\033[36m[4/7] 检测环境配置文件...\033[0m"
    ENV_FILE="$SCRIPT_DIR/.env"
    ENV_EXAMPLE="$SCRIPT_DIR/.env.example"

    if [ -f "$ENV_FILE" ]; then
        echo -e "\033[32m.env 文件已存在\033[0m"
    else
        if [ -f "$ENV_EXAMPLE" ]; then
            echo -e "\033[33m正在从 .env.example 复制配置文件...\033[0m"
            cp "$ENV_EXAMPLE" "$ENV_FILE"
            echo -e "\033[32m.env 文件已创建，请编辑填写 API 密钥！\033[0m"
        else
            echo -e "\033[33m.env.example 不存在，跳过\033[0m"
        fi
    fi

    echo -e "\n\033[36m[5/7] 安装 Python 依赖...\033[0m"
    REQUIREMENTS_FILE="$SCRIPT_DIR/requirements.txt"
    if [ -f "$REQUIREMENTS_FILE" ]; then
        uv pip install -r "$REQUIREMENTS_FILE"
        if [ $? -ne 0 ]; then
            echo -e "\033[31mPython 依赖安装失败，但将继续执行后续步骤\033[0m"
        else
            echo -e "\033[32mPython 依赖安装完成\033[0m"
        fi
    else
        echo -e "\033[33mrequirements.txt 不存在，跳过\033[0m"
    fi

    echo -e "\n\033[36m[6/7] 下载嵌入模型...\033[0m"
    
    # 检查模型是否已存在
    MODEL_CACHE_DIR="$HOME/.cache/huggingface/hub"
    if [ -d "$MODEL_CACHE_DIR" ]; then
        if ls "$MODEL_CACHE_DIR"/*bge-small-zh* 1>/dev/null 2>&1; then
            echo -e "\033[32m检测到嵌入模型已存在，跳过下载\033[0m"
        else
            echo -e "\033[33m请选择模型下载方式:\033[0m"
            echo -e "  \033[36m1\033[0m) 使用 Hugging Face (download_embedding_model.py)"
            echo -e "  \033[36m2\033[0m) 使用 ModelScope (download_model_via_modelscope.py) - 国内推荐"
            read -p "请选择 [1-2]: " model_choice
            
            case $model_choice in
                1)
                    MODEL_SCRIPT="$SCRIPT_DIR/scripts/utils/download_embedding_model.py"
                    echo -e "\033[32m使用 Hugging Face 下载嵌入模型...\033[0m"
                    ;;
                2|*)
                    MODEL_SCRIPT="$SCRIPT_DIR/scripts/utils/download_model_via_modelscope.py"
                    echo -e "\033[32m使用 ModelScope 下载嵌入模型...\033[0m"
                    
                    # 确保 pip 可用
                    if ! command -v pip &> /dev/null && ! command -v pip3 &> /dev/null; then
                        echo -e "\033[33m检测到虚拟环境中没有 pip，正在安装...\033[0m"
                        uv pip install pip
                        if [ $? -ne 0 ]; then
                            echo -e "\033[31mpip 安装失败，切换到 Hugging Face 方案...\033[0m"
                            MODEL_SCRIPT="$SCRIPT_DIR/scripts/utils/download_embedding_model.py"
                            echo -e "\033[32m使用 Hugging Face 下载嵌入模型...\033[0m"
                        fi
                    fi
                    ;;
            esac
            
            if [ -f "$MODEL_SCRIPT" ]; then
                uv run python "$MODEL_SCRIPT"
                if [ $? -ne 0 ]; then
                    echo -e "\033[31m模型下载失败，请检查网络连接\033[0m"
                    
                    # 尝试备用方案
                    if [ "$MODEL_SCRIPT" = "$SCRIPT_DIR/scripts/utils/download_model_via_modelscope.py" ]; then
                        echo -e "\033[33m尝试使用 Hugging Face 方案...\033[0m"
                        MODEL_SCRIPT="$SCRIPT_DIR/scripts/utils/download_embedding_model.py"
                        if [ -f "$MODEL_SCRIPT" ]; then
                            uv run python "$MODEL_SCRIPT"
                            if [ $? -eq 0 ]; then
                                echo -e "\033[32m模型下载完成（使用备用方案）\033[0m"
                            fi
                        fi
                    fi
                else
                    echo -e "\033[32m嵌入模型下载完成\033[0m"
                fi
            else
                echo -e "\033[33m模型下载脚本不存在: $MODEL_SCRIPT\033[0m"
                
                # 尝试备用脚本
                if [ "$MODEL_SCRIPT" = "$SCRIPT_DIR/scripts/utils/download_model_via_modelscope.py" ]; then
                    ALTERNATIVE_SCRIPT="$SCRIPT_DIR/scripts/utils/download_embedding_model.py"
                    if [ -f "$ALTERNATIVE_SCRIPT" ]; then
                        echo -e "\033[33m尝试使用备用脚本: $ALTERNATIVE_SCRIPT\033[0m"
                        uv run python "$ALTERNATIVE_SCRIPT"
                        if [ $? -eq 0 ]; then
                            echo -e "\033[32m模型下载完成（使用备用方案）\033[0m"
                        fi
                    fi
                fi
            fi
        fi
    else
        echo -e "\033[33m请选择模型下载方式:\033[0m"
        echo -e "  \033[36m1\033[0m) 使用 Hugging Face (download_embedding_model.py)"
        echo -e "  \033[36m2\033[0m) 使用 ModelScope (download_model_via_modelscope.py) - 国内推荐"
        read -p "请选择 [1-2]: " model_choice
        
        case $model_choice in
            1)
                MODEL_SCRIPT="$SCRIPT_DIR/scripts/utils/download_embedding_model.py"
                echo -e "\033[32m使用 Hugging Face 下载嵌入模型...\033[0m"
                ;;
            2|*)
                MODEL_SCRIPT="$SCRIPT_DIR/scripts/utils/download_model_via_modelscope.py"
                echo -e "\033[32m使用 ModelScope 下载嵌入模型...\033[0m"
                
                # 确保 pip 可用
                if ! command -v pip &> /dev/null && ! command -v pip3 &> /dev/null; then
                    echo -e "\033[33m检测到虚拟环境中没有 pip，正在安装...\033[0m"
                    uv pip install pip
                    if [ $? -ne 0 ]; then
                        echo -e "\033[31mpip 安装失败，切换到 Hugging Face 方案...\033[0m"
                        MODEL_SCRIPT="$SCRIPT_DIR/scripts/utils/download_embedding_model.py"
                        echo -e "\033[32m使用 Hugging Face 下载嵌入模型...\033[0m"
                    fi
                fi
                ;;
        esac
        
        if [ -f "$MODEL_SCRIPT" ]; then
            uv run python "$MODEL_SCRIPT"
            if [ $? -ne 0 ]; then
                echo -e "\033[31m模型下载失败，请检查网络连接\033[0m"
                
                # 尝试备用方案
                if [ "$MODEL_SCRIPT" = "$SCRIPT_DIR/scripts/utils/download_model_via_modelscope.py" ]; then
                    echo -e "\033[33m尝试使用 Hugging Face 方案...\033[0m"
                    MODEL_SCRIPT="$SCRIPT_DIR/scripts/utils/download_embedding_model.py"
                    if [ -f "$MODEL_SCRIPT" ]; then
                        uv run python "$MODEL_SCRIPT"
                        if [ $? -eq 0 ]; then
                            echo -e "\033[32m模型下载完成（使用备用方案）\033[0m"
                        fi
                    fi
                fi
            else
                echo -e "\033[32m嵌入模型下载完成\033[0m"
            fi
        else
            echo -e "\033[33m模型下载脚本不存在: $MODEL_SCRIPT\033[0m"
            
            # 尝试备用脚本
            if [ "$MODEL_SCRIPT" = "$SCRIPT_DIR/scripts/utils/download_model_via_modelscope.py" ]; then
                ALTERNATIVE_SCRIPT="$SCRIPT_DIR/scripts/utils/download_embedding_model.py"
                if [ -f "$ALTERNATIVE_SCRIPT" ]; then
                    echo -e "\033[33m尝试使用备用脚本: $ALTERNATIVE_SCRIPT\033[0m"
                    uv run python "$ALTERNATIVE_SCRIPT"
                    if [ $? -eq 0 ]; then
                        echo -e "\033[32m模型下载完成（使用备用方案）\033[0m"
                    fi
                fi
            fi
        fi
    fi

    echo -e "\n\033[36m[7/7] 安装前端依赖...\033[0m"
    FRONTEND_DIR="$SCRIPT_DIR/frontend"
    if [ -d "$FRONTEND_DIR" ]; then
        cd "$FRONTEND_DIR"
        if [ -d "node_modules" ]; then
            if ! ask_reinstall "前端依赖目录" "$FRONTEND_DIR/node_modules"; then
                echo -e "\033[32m使用现有的前端依赖\033[0m"
            else
                echo -e "\033[33m正在删除现有前端依赖...\033[0m"
                rm -rf "node_modules"
                echo -e "\033[33m正在安装前端依赖...\033[0m"
                npm install
                if [ $? -ne 0 ]; then
                    echo -e "\033[31m前端依赖安装失败，但将继续执行后续步骤\033[0m"
                else
                    echo -e "\033[32m前端依赖安装完成\033[0m"
                fi
            fi
        else
            npm install
            if [ $? -ne 0 ]; then
                echo -e "\033[31m前端依赖安装失败，但将继续执行后续步骤\033[0m"
            else
                echo -e "\033[32m前端依赖安装完成\033[0m"
            fi
        fi
        cd "$SCRIPT_DIR"
    else
        echo -e "\033[33m前端目录不存在: $FRONTEND_DIR\033[0m"
    fi

    echo -e "\n\033[36m[8/8] 安装 Docker（可选）...\033[0m"
    read -p "是否安装 Docker（用于运行 Qdrant 向量数据库）？ [1/跳过]: " install_docker
    if [[ "$install_docker" == "1" ]]; then
        local docker_cmd=""

        if command -v docker &> /dev/null; then
            if docker info &> /dev/null; then
                docker_cmd="docker"
            elif sudo docker info &> /dev/null; then
                docker_cmd="sudo docker"
            else
                echo -e "\033[31m无法访问 Docker，请检查权限配置\033[0m"
                docker_cmd=""
            fi
        else
            echo -e "\033[33m正在安装 Docker...\033[0m"
            if command -v apt-get &> /dev/null; then
                sudo apt-get update
                sudo apt-get install -y docker.io docker-compose
            elif command -v brew &> /dev/null; then
                brew install docker docker-compose
            elif command -v pacman &> /dev/null; then
                sudo pacman -S docker docker-compose
            else
                echo -e "\033[31m无法自动安装 Docker，请手动安装\033[0m"
            fi

            if sudo docker info &> /dev/null; then
                docker_cmd="sudo docker"
            else
                echo -e "\033[31mDocker 安装后仍无法访问，请检查权限\033[0m"
            fi
        fi

        if [ -n "$docker_cmd" ]; then
            echo -e "\033[36m启动 Qdrant 向量数据库...\033[0m"
            if [ -f "$SCRIPT_DIR/docker-compose.yml" ]; then
                $docker_cmd compose up -d
                if [ $? -eq 0 ]; then
                    echo -e "\033[32mQdrant 已启动，运行在 http://localhost:6333\033[0m"
                else
                    echo -e "\033[31mQdrant 启动失败\033[0m"
                fi
            else
                echo -e "\033[33mdocker-compose.yml 文件不存在，跳过启动 Qdrant\033[0m"
            fi
        else
            echo -e "\033[33m跳过 Qdrant 启动\033[0m"
        fi
    else
        echo -e "\033[33m跳过 Docker 安装\033[0m"
    fi

    echo -e "\n\033[35m========================================\033[0m"
    echo -e "\033[32m  懒人安装完成！\033[0m"
    echo -e "\033[35m========================================\033[0m"
    echo -e "\033[33m提示: 请记得编辑 .env 文件填写 API 密钥\033[0m"

    return 0
}

while true; do
    show_menu

    read -p "请选择操作 (0-6): " choice

    case $choice in
        1)
            start_both
            echo ""
            echo "按任意键返回菜单..."
            read -n 1 -s
            ;;
        2)
            start_backend
            echo ""
            echo "按任意键返回菜单..."
            read -n 1 -s
            ;;
        3)
            start_frontend
            echo ""
            echo "按任意键返回菜单..."
            read -n 1 -s
            ;;
        4)
            start_qdrant
            echo ""
            echo "按任意键返回菜单..."
            read -n 1 -s
            ;;
        5)
            run_tests
            echo ""
            echo "按任意键返回菜单..."
            read -n 1 -s
            ;;
        6)
            lazy_install
            echo ""
            echo "按任意键返回菜单..."
            read -n 1 -s
            ;;
        0)
            echo -e "\n\033[36m再见！\033[0m"
            exit 0
            ;;
        *)
            echo -e "\n\033[31m无效选择，请重新输入！\033[0m"
            sleep 1
            ;;
    esac
done
