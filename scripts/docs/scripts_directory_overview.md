# scripts 目录直属内容功能说明

## 📁 目录结构概览

```
scripts/
├── __pycache__/          # Python字节码缓存目录
├── docs/                 # 脚本文档目录
├── automatic_update.bat  # 自动更新批处理脚本
├── install_service.bat   # 服务安装脚本
├── nssm.exe             # Windows服务管理器
├── pyinstaller_packager.py # Python打包脚本
└── uninstall_service.bat # 服务卸载脚本
```

## 📋 直属目录和文件功能说明

### 📁 目录说明

#### `__pycache__/`
- **功能**: Python字节码缓存目录
- **作用**: 存储编译后的Python字节码文件，提升模块加载速度
- **包含文件**:
  - `hash_generator.cpython-39.pyc` - MD5计算模块缓存
  - `pyinstaller_packager.cpython-39.pyc` - 打包脚本缓存

#### `docs/`
- **功能**: 脚本文档目录
- **作用**: 提供详细的脚本使用说明和功能文档
- **包含文档**:
  - `README.md` - 总体功能说明
  - `pyinstaller_packager.md` - 打包脚本详细说明
  - `automatic_update.md` - 自更新脚本说明
  - `service_management.md` - 服务管理脚本说明
  - `scripts_directory_overview.md` - 本目录结构说明

### 📄 文件说明

#### `pyinstaller_packager.py`
- **类型**: Python脚本
- **功能**: 项目打包工具
- **作用**: 将Python应用打包为单个可执行文件
- **输出**: `dist/local_agent.exe`
- **使用方式**: 根据项目规则，唯一正确的启动方式为运行此脚本

#### `automatic_update.bat`
- **类型**: Windows批处理脚本
- **功能**: 自动更新管理器
- **作用**: 实现应用自更新和回滚机制
- **参数**: 服务名、新旧文件路径、备份目录

#### `install_service.bat`
- **类型**: Windows批处理脚本
- **功能**: Windows服务安装脚本
- **作用**: 使用NSSM将应用安装为Windows服务
- **依赖**: 需要 `nssm.exe` 文件

#### `uninstall_service.bat`
- **类型**: Windows批处理脚本
- **功能**: Windows服务卸载脚本
- **作用**: 安全卸载已安装的服务
- **特性**: 包含服务存在性检查和用户确认机制

#### `nssm.exe`
- **类型**: Windows可执行文件
- **功能**: Windows服务管理器
- **作用**: 用于将普通应用程序安装为Windows服务
- **来源**: Non-Sucking Service Manager 开源工具
- **类型**: Windows批处理脚本
- **功能**: 服务安装工具
- **作用**: 使用NSSM将应用安装为Windows服务
- **配置**: 自动启动、日志输出、服务参数

#### `uninstall_service.bat`
- **类型**: Windows批处理脚本
- **功能**: 服务卸载工具
- **作用**: 安全卸载已安装的Windows服务
- **特性**: 用户确认、安全停止、服务删除

#### `nssm.exe`
- **类型**: 可执行程序
- **功能**: Non-Sucking Service Manager
- **作用**: 轻量级Windows服务管理器
- **用途**: 将普通应用安装为Windows服务

## 🔄 脚本间协作关系

```
pyinstaller_packager.py (生成exe)
    ↓
install_service.bat (安装服务)
    ↓
automatic_update.bat (自更新)
    ↓
uninstall_service.bat (卸载服务)
```

## 💡 使用场景

### 开发阶段
- 直接运行Python源码，无需脚本

### 打包部署
1. 运行 `pyinstaller_packager.py` 打包应用
2. 可选运行 `install_service.bat` 安装服务
3. 通过 `automatic_update.bat` 实现更新

### 维护阶段
- 使用 `uninstall_service.bat` 卸载服务
- 通过自更新机制维护应用版本

## ⚠️ 注意事项

- **权限要求**: 自更新和服务安装需要管理员权限
- **路径配置**: 部分脚本中的路径为硬编码，需根据环境修改
- **依赖检查**: 脚本会自动检查必要的依赖和工具
- **日志记录**: 所有操作都有详细的日志记录