"""环境检查脚本：确保验证原型可以运行"""
import sys
from pathlib import Path

def check_python_version():
    """检查 Python 版本"""
    version = sys.version_info
    if version.major >= 3 and version.minor >= 9:
        print(f"✅ Python 版本: {version.major}.{version.minor}.{version.micro}")
        return True
    else:
        print(f"❌ Python 版本过低: {version.major}.{version.minor}.{version.micro}")
        print("   需要 Python 3.9+")
        return False

def check_dependencies():
    """检查依赖包"""
    required = {
        "anthropic": "anthropic",
        "pydantic": "pydantic",
        "python-dotenv": "dotenv"
    }

    missing = []
    for package_name, import_name in required.items():
        try:
            __import__(import_name)
            print(f"✅ {package_name}")
        except ImportError:
            print(f"❌ {package_name} 未安装")
            missing.append(package_name)

    if missing:
        print(f"\n请运行: pip install {' '.join(missing)}")
        return False
    return True

def check_env_file():
    """检查 .env 文件"""
    env_file = Path(__file__).parent.parent / ".env"
    if env_file.exists():
        print(f"✅ .env 文件存在")

        # 检查是否有 API key
        with open(env_file, 'r') as f:
            content = f.read()
            if "ANTHROPIC_API_KEY" in content:
                print("✅ ANTHROPIC_API_KEY 已配置")
                return True
            else:
                print("⚠️  ANTHROPIC_API_KEY 未配置（模拟版不需要）")
                return True
    else:
        print(f"⚠️  .env 文件不存在（模拟版不需要）")
        return True

def check_output_dir():
    """检查输出目录"""
    output_dir = Path(__file__).parent.parent / "data" / "prototype_results"
    if not output_dir.exists():
        output_dir.mkdir(parents=True, exist_ok=True)
        print(f"✅ 创建输出目录: {output_dir}")
    else:
        print(f"✅ 输出目录存在: {output_dir}")
    return True

def main():
    print("=" * 60)
    print("环境检查")
    print("=" * 60)
    print()

    checks = [
        ("Python 版本", check_python_version),
        ("依赖包", check_dependencies),
        (".env 文件", check_env_file),
        ("输出目录", check_output_dir),
    ]

    results = []
    for name, check_func in checks:
        print(f"\n检查 {name}:")
        results.append(check_func())

    print("\n" + "=" * 60)
    if all(results):
        print("✅ 所有检查通过！可以启动后端与前端进行开发。")
    else:
        print("❌ 部分检查失败，请先解决上述问题。")
    print("=" * 60)

if __name__ == "__main__":
    main()
