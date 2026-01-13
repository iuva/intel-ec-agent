# 脚本目录功能说明

本目录包含项目构建、部署和运维相关的自动化脚本。

## 📋 文件功能概览

### 📦 构建脚本
- `pyinstaller_packager.py` - Python项目打包工具，生成可执行文件

### 🔄 自更新脚本  
- `automatic_update.bat` - 自动更新管理器，支持回滚机制

### 🛠️ 服务管理脚本
- `install_service.bat` - Windows服务安装脚本
- `uninstall_service.bat` - Windows服务卸载脚本
- `nssm.exe` - Windows服务管理器工具

### 📚 文档目录
- `docs/` - 详细的脚本使用说明和功能文档

## 🚀 使用说明

根据项目规则，唯一正确的启动方式为：
```bash
# 1. 打包应用（开发阶段）
python scripts/pyinstaller_packager.py

# 2. 以管理员身份运行打包后的exe（生产环境）
右键管理员运行 dist/local_agent.exe
```

### 🔧 工具文件

#### `nssm.exe`
- **功能**: Non-Sucking Service Manager
- **作用**: 轻量级的Windows服务管理器
- **用途**: 用于将普通应用安装为Windows服务

#### `__pycache__/`
- **功能**: Python字节码缓存目录
- **作用**: 存储编译后的Python字节码文件
- **包含**:
  - `hash_generator.cpython-39.pyc` - MD5计算模块缓存
  - `pyinstaller_packager.cpython-39.pyc` - 打包脚本缓存

## 使用流程

### 标准构建流程
1. **打包应用**: 运行 `pyinstaller_packager.py`
2. **安装服务**: 运行 `install_service.bat`（可选）
3. **自更新**: 通过 `automatic_update.bat` 实现

### 开发阶段
- 直接运行 `python src/local_agent/__main__.py`

### 生产环境
- 使用打包后的 `dist/local_agent.exe`

## 注意事项

1. **权限要求**: 自更新和服务安装需要管理员权限
2. **依赖检查**: 脚本会自动检查必要的依赖
3. **日志记录**: 所有操作都有详细的日志记录
4. **错误处理**: 包含完善的错误处理和回滚机制

## 版本兼容性

- Python 3.8+
- Windows 7/10/11
- 支持32位和64位系统