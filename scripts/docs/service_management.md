# 服务管理脚本

## 功能概述

服务管理脚本用于将应用安装为Windows服务，实现开机自启动和后台运行。

## 脚本文件

### `install_service.bat` - 服务安装脚本

#### 主要功能
- **服务安装**: 使用NSSM安装Windows服务
- **参数配置**: 自动配置服务参数
- **状态检查**: 验证服务安装状态
- **日志配置**: 设置服务日志输出

#### 使用参数
```bash
install_service.bat
```

#### 配置参数（硬编码）
- **服务名称**: `LocalAgentService`
- **可执行文件路径**: `F:\testPc\dragTest\dist\local_agent.exe`
- **工作目录**: `F:\testPc\dragTest\dist`

#### 服务配置
- **描述**: "本地代理服务 - 提供API接口和WebSocket连接"
- **显示名称**: "本地代理服务"
- **启动类型**: 自动启动
- **日志输出**: `service.log` 和 `service_error.log`

### `uninstall_service.bat` - 服务卸载脚本

#### 主要功能
- **服务检查**: 验证服务存在性
- **用户确认**: 安全卸载确认
- **服务停止**: 停止运行的服务
- **服务删除**: 移除服务注册

#### 使用参数
```bash
uninstall_service.bat
```

## NSSM 工具

### `nssm.exe`
- **功能**: Non-Sucking Service Manager
- **作用**: 轻量级Windows服务管理器
- **特点**: 简单易用，无需.NET Framework

### NSSM 常用命令
```bash
# 安装服务
nssm install <service_name> <exe_path>

# 启动服务
nssm start <service_name>

# 停止服务
nssm stop <service_name>

# 重启服务
nssm restart <service_name>

# 卸载服务
nssm remove <service_name>

# 查看状态
nssm status <service_name>
```

## 使用流程

### 安装服务
1. 确保NSSM可用
2. 运行 `install_service.bat`
3. 确认服务安装
4. 检查服务状态

### 卸载服务
1. 运行 `uninstall_service.bat`
2. 确认卸载操作
3. 验证服务删除

## 注意事项

### 权限要求
- 需要管理员权限
- 服务安装权限
- 文件系统访问权限

### 路径配置
- 脚本中的路径为硬编码
- 需要根据实际环境修改
- 确保路径存在且可访问

### 依赖检查
- 自动检测NSSM可用性
- 服务存在性验证
- 错误处理机制

## 故障排除

### 常见问题
1. **NSSM未找到**: 下载并配置NSSM
2. **权限不足**: 以管理员身份运行
3. **路径错误**: 检查文件路径配置
4. **服务冲突**: 检查服务名称重复

### 调试方法
- 查看脚本输出信息
- 检查服务日志文件
- 使用NSSM命令行工具
- 查看Windows事件日志