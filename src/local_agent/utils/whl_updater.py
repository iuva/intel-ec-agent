#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
WHL包覆盖更新工具
根据whl包URL进行软件覆盖更新，支持断点续传和错误重试

主要功能：
1. 下载whl包文件
2. 使用pip进行覆盖安装
3. 支持回滚机制
4. 完整的日志记录

使用示例：
    from local_agent.utils.whl_updater import update_from_whl
    success = update_from_whl("https://example.com/package-1.0.0-py3-none-any.whl")
"""

import os
import sys
import time
import tempfile
import shutil
import re
from pathlib import Path
from typing import Optional, Tuple

# 导入项目全局组件
from ..logger import get_logger
# 导入增强的子进程工具
from .subprocess_utils import run_with_logging, run_with_logging_safe
# 延迟导入以避免循环依赖
def _get_download_file():
    from .file_downloader import download_file_async
    return download_file_async

download_file = None  # 延迟初始化
from .python_utils import PythonUtils
from .path_utils import PathUtils


class WhlUpdater:
    """WHL包覆盖更新工具类"""
    
    def __init__(self):
        """初始化更新器"""
        self.logger = get_logger(__name__)
        self.temp_dir = PathUtils.get_root_path() / "whl_updates"
        self.temp_dir.mkdir(parents=True, exist_ok=True)
        
        # 配置参数
        self.max_retries = 3
        self.timeout = 600  # 10分钟超时
        self.backup_enabled = True
        
        self.logger.info(f"WHL更新器初始化完成，临时目录: {self.temp_dir}")
    
    def _get_python_executable(self) -> Optional[str]:
        """
        获取Python可执行文件路径，使用Python工具类
        
        Returns:
            Optional[str]: Python可执行文件路径，如果未找到返回None
        """
        try:
            python_path = PythonUtils.get_python_check()
            if python_path:
                self.logger.info(f"获取Python路径: {python_path}")
                return python_path
            else:
                self.logger.warning("未找到可用的Python路径")
                return None
        except Exception as e:
            self.logger.error(f"获取Python路径失败: {e}")
            return None
    
    async def _download_whl_file(self, whl_url: str) -> Optional[Path]:
        """
        下载whl包文件
        
        Args:
            whl_url: whl包下载URL
            version: 版本号
            
        Returns:
            Optional[Path]: 下载的whl文件路径，如果失败返回None
        """
        try:
            # 从URL提取文件名
            filename = whl_url.split('/')[-1]
            if not filename.endswith('.whl'):
                self.logger.error(f"URL格式错误，不是有效的whl文件: {whl_url}")
                return None
            
            # 保存路径
            save_path = self.temp_dir / filename
            
            self.logger.info(f"开始下载whl包: {whl_url}")
            self.logger.info(f"保存到: {save_path}")
            
            # 延迟加载下载函数
            global download_file
            if download_file is None:
                download_file = _get_download_file()
            
            # 使用项目统一的文件下载器
            success = await download_file(whl_url, str(save_path))
            
            if success and save_path.exists():
                file_size = save_path.stat().st_size
                self.logger.info(f"whl包下载成功，文件大小: {self._format_size(file_size)}")
                
                # 验证WHL文件完整性
                if not self._validate_whl_integrity(save_path):
                    self.logger.error("❌ WHL文件完整性验证失败，可能文件损坏或不完整")
                    # 删除损坏的文件
                    try:
                        save_path.unlink()
                        self.logger.info("已删除损坏的WHL文件")
                    except Exception as e:
                        self.logger.error(f"删除损坏文件失败: {e}")
                    return None
                
                self.logger.info("✅ WHL文件完整性验证通过")
                
                # 下载完成后，强制根据WHL包内部信息进行重命名
                original_filename = save_path.name
                self.logger.info(f"下载完成，原始文件名: {original_filename}")
                self.logger.info("执行强制重命名（硬性执行标准）...")
                
                # 从WHL文件中读取包信息进行重命名
                package_info = self._extract_package_info_from_whl(save_path)
                if package_info and package_info.get('name') and package_info.get('version'):
                    package_name = package_info['name']
                    package_version = package_info['version']
                    
                    # 生成新的文件名
                    new_filename = f"{package_name}-{package_version}-py3-none-any.whl"
                    
                    self.logger.info(f"从WHL文件中提取包信息: {package_name} {package_version}")
                    self.logger.info(f"执行强制重命名: {original_filename} -> {new_filename}")
                    
                    if new_filename != original_filename:
                        new_whl_path = self.temp_dir / new_filename
                        try:
                            # 确保目标文件不存在
                            if new_whl_path.exists():
                                new_whl_path.unlink()
                            
                            save_path.rename(new_whl_path)
                            self.logger.info(f"✅ 文件重命名成功: {original_filename} -> {new_whl_path.name}")
                            save_path = new_whl_path
                        except Exception as rename_error:
                            self.logger.error(f"❌ 文件重命名失败: {rename_error}")
                            # 记录详细的错误信息以便调试
                            self.logger.debug(f"重命名失败详情: 源文件={save_path}, 目标文件={new_whl_path}")
                else:
                    self.logger.warning("⚠️ 无法从WHL文件中提取包信息，使用原始文件名")
                
                # 记录最终文件名
                final_filename = save_path.name
                self.logger.info(f"最终文件名: {final_filename}")
                
                return save_path
            else:
                self.logger.error("whl包下载失败")
                return None
                
        except Exception as e:
            self.logger.error(f"下载whl包时发生错误: {e}")
            return None
    
    def _install_whl_package(self, whl_path: Path, python_path: str) -> Tuple[bool, str]:
        """
        使用pip安装whl包
        
        Args:
            whl_path: whl文件路径
            python_path: Python可执行文件路径
            
        Returns:
            Tuple[bool, str]: (安装是否成功, 错误信息)
        """
        try:
            # 构建pip安装命令
            pip_command = [
                python_path, "-m", "pip", "install", 
                "--upgrade", "--force-reinstall", "--no-deps",
                str(whl_path)
            ]
            
            self.logger.info(f"开始安装whl包: {whl_path.name}")
            self.logger.debug(f"安装命令: {' '.join(pip_command)}")
            
            # 执行pip安装
            result = run_with_logging(
                pip_command,
                command_name="pip_install_whl",
                capture_output=True,
                text=True,
                timeout=self.timeout,
                encoding='utf-8',
                errors='ignore'
            )
            
            # 记录安装结果
            if result.stdout:
                self.logger.info(f"pip安装输出: {result.stdout.strip()}")
            
            # 检查stderr中是否有警告信息
            if result.stderr:
                stderr_content = result.stderr.strip()
                self.logger.warning(f"pip安装警告: {stderr_content}")
                
                # 检查是否包含"Ignoring invalid distribution"警告
                if "Ignoring invalid distribution" in stderr_content:
                    self.logger.warning("检测到无效的包分发目录，尝试清理后重新安装")
                    
                    # 尝试清理无效分发
                    cleanup_success = self._cleanup_invalid_distributions(python_path)
                    if cleanup_success:
                        self.logger.info("无效分发清理完成，重新尝试安装")
                        # 重新执行安装
                        result = run_with_logging(
                            pip_command,
                            command_name="pip_install_retry",
                            capture_output=True,
                            text=True,
                            timeout=self.timeout,
                            encoding='utf-8',
                            errors='ignore'
                        )
            
            if result.returncode == 0:
                self.logger.info("whl包安装成功")
                return True, ""
            else:
                error_msg = result.stderr.strip() if result.stderr else "未知错误"
                self.logger.error(f"whl包安装失败: {error_msg}")
                return False, error_msg
                
        except Exception as e:
            error_msg = f"执行pip安装时发生错误: {e}"
            self.logger.error(error_msg)
            return False, error_msg
    
    def _cleanup_invalid_distributions(self, python_path: str) -> bool:
        """
        清理无效的包分发目录
        
        Args:
            python_path: Python可执行文件路径
            
        Returns:
            bool: 清理是否成功
        """
        try:
            # 使用pip check命令检查无效分发
            check_command = [python_path, "-m", "pip", "check"]
            result = run_with_logging(check_command, command_name="pip_check", capture_output=True, text=True)
            
            if result.returncode != 0:
                self.logger.warning(f"检测到包环境问题: {result.stdout.strip()}")
                
                # 尝试使用pip cache purge清理缓存
                cache_command = [python_path, "-m", "pip", "cache", "purge"]
                cache_result = run_with_logging(cache_command, command_name="pip_cache_purge", capture_output=True, text=True)
                
                if cache_result.returncode == 0:
                    self.logger.info("pip缓存清理成功")
                else:
                    self.logger.warning(f"pip缓存清理失败: {cache_result.stderr.strip()}")
                
                # 尝试修复包环境
                fix_command = [python_path, "-m", "pip", "install", "--upgrade", "pip", "setuptools", "wheel"]
                fix_result = run_with_logging(fix_command, command_name="pip_tools_upgrade", capture_output=True, text=True)
                
                if fix_result.returncode == 0:
                    self.logger.info("pip工具更新成功")
                    return True
                else:
                    self.logger.warning(f"pip工具更新失败: {fix_result.stderr.strip()}")
                    return False
            
            self.logger.info("包环境检查正常")
            return True
            
        except Exception as e:
            self.logger.error(f"清理无效分发时发生错误: {e}")
            return False
    
    def _create_backup(self, package_name: str) -> bool:
        """
        创建当前包备份
        
        Args:
            package_name: 包名称
            
        Returns:
            bool: 备份是否成功
        """
        if not self.backup_enabled:
            return True
            
        try:
            python_path = self._get_python_executable()
            if not python_path:
                self.logger.warning("无法获取Python路径，跳过备份")
                return False
            
            # 获取当前安装版本
            freeze_command = [python_path, "-m", "pip", "freeze", "--all"]
            result = run_with_logging(freeze_command, command_name="pip_freeze", capture_output=True, text=True)
            
            if result.returncode == 0:
                # 查找包信息
                for line in result.stdout.strip().split('\n'):
                    if line.startswith(package_name + '=='):
                        version = line.split('==')[1]
                        backup_info = f"{package_name}=={version}"
                        
                        # 保存备份信息
                        backup_file = self.temp_dir / f"{package_name}_backup.txt"
                        with open(backup_file, 'w', encoding='utf-8') as f:
                            f.write(backup_info)
                        
                        self.logger.info(f"创建备份: {backup_info}")
                        return True
            
            self.logger.warning(f"未找到包 {package_name} 的当前安装信息")
            return False
            
        except Exception as e:
            self.logger.error(f"创建备份失败: {e}")
            return False
    
    def _rollback_package(self, package_name: str) -> bool:
        """
        回滚包到备份版本
        
        Args:
            package_name: 包名称
            
        Returns:
            bool: 回滚是否成功
        """
        try:
            python_path = self._get_python_executable()
            if not python_path:
                return False
            
            # 读取备份信息
            backup_file = self.temp_dir / f"{package_name}_backup.txt"
            if not backup_file.exists():
                self.logger.warning("未找到备份文件，无法回滚")
                return False
            
            with open(backup_file, 'r', encoding='utf-8') as f:
                backup_info = f.read().strip()
            
            # 执行回滚安装
            rollback_command = [python_path, "-m", "pip", "install", backup_info]
            result = run_with_logging(rollback_command, command_name="pip_rollback", capture_output=True, text=True)
            
            if result.returncode == 0:
                self.logger.info(f"回滚成功: {backup_info}")
                return True
            else:
                self.logger.error(f"回滚失败: {result.stderr}")
                return False
                
        except Exception as e:
            self.logger.error(f"回滚时发生错误: {e}")
            return False
    
    def _is_valid_whl_filename(self, filename: str) -> bool:
        """
        验证WHL文件名是否符合PEP 427规范
        
        Args:
            filename: 文件名
            
        Returns:
            bool: 是否有效
        """
        if not filename.endswith('.whl'):
            return False
        
        # 移除.whl后缀
        base_name = filename[:-4]
        parts = base_name.split('-')
        
        # 有效的WHL文件名应该至少有4个部分：包名-版本-py标签-平台标签
        if len(parts) < 3:
            return False
        
        # 检查是否有版本号（版本号通常以数字开头）
        has_version = any(part and part[0].isdigit() for part in parts)
        
        # 检查是否有Python标签（包含'py'或'cp'）
        has_python_tag = any('py' in part.lower() or 'cp' in part.lower() for part in parts)
        
        # 检查包名是否为通用名称（如'package'），如果是则视为无效
        package_name = parts[0]
        generic_package_names = ['package', 'test', 'temp', 'unknown', 'whl']
        has_generic_name = package_name.lower() in generic_package_names
        
        # 额外验证：检查包名是否符合PEP 427规范
        is_valid_package_name = self._is_valid_package_name(package_name)
        
        return has_version and has_python_tag and not has_generic_name and is_valid_package_name
    
    def _extract_package_info_from_whl(self, whl_path: Path) -> Optional[dict]:
        """
        从WHL文件中提取包信息（名称、版本等）
        
        Args:
            whl_path: WHL文件路径
            
        Returns:
            Optional[dict]: 包含包信息的字典，如果失败返回None
        """
        try:
            import zipfile
            import tempfile
            import os
            
            # WHL文件本质上是zip压缩包
            with zipfile.ZipFile(whl_path, 'r') as whl_zip:
                # 查找包含元数据的文件 - 放宽条件，查找所有.dist-info和.egg-info目录
                metadata_files = []
                for filename in whl_zip.namelist():
                    # 匹配任何.dist-info/METADATA或.egg-info/PKG-INFO文件
                    if (filename.endswith('/METADATA') and '.dist-info' in filename) or \
                       (filename.endswith('/PKG-INFO') and '.egg-info' in filename):
                        metadata_files.append(filename)
                
                if not metadata_files:
                    self.logger.warning(f"在WHL文件中未找到元数据文件: {whl_path}")
                    return None
                
                # 使用第一个找到的元数据文件
                metadata_file = metadata_files[0]
                self.logger.info(f"找到元数据文件: {metadata_file}")
                
                # 提取元数据文件内容
                with whl_zip.open(metadata_file) as f:
                    metadata_content = f.read().decode('utf-8', errors='ignore')
                
                # 解析元数据
                package_info = {}
                for line in metadata_content.split('\n'):
                    line = line.strip()
                    if line.startswith('Name:'):
                        package_info['name'] = line.split(':', 1)[1].strip()
                    elif line.startswith('Version:'):
                        package_info['version'] = line.split(':', 1)[1].strip()
                    elif line.startswith('Summary:'):
                        package_info['summary'] = line.split(':', 1)[1].strip()
                    elif line.startswith('Author:'):
                        package_info['author'] = line.split(':', 1)[1].strip()
                    
                    # 如果已经找到包名和版本，可以提前退出
                    if 'name' in package_info and 'version' in package_info:
                        break
                
                if 'name' in package_info and 'version' in package_info:
                    self.logger.info(f"成功从WHL文件中提取包信息: {package_info['name']} {package_info['version']}")
                    return package_info
                else:
                    self.logger.warning(f"从WHL文件中提取包信息不完整: {package_info}")
                    return None
                    
        except Exception as e:
            self.logger.warning(f"从WHL文件中提取包信息时发生错误: {e}")
            return None
    
    def _extract_package_name(self, whl_filename: str) -> str:
        """
        从whl文件名提取包名称
        
        Args:
            whl_filename: whl文件名
            
        Returns:
            str: 包名称
        """
        # whl文件名格式: package_name-version-py3-none-any.whl
        # 提取包名称（第一个连字符之前的部分）
        base_name = whl_filename.replace('.whl', '')
        parts = base_name.split('-')
        
        # 包名称通常是第一个连字符之前的部分
        # 但有些包可能有多个连字符，需要找到版本号开始的位置
        for i, part in enumerate(parts):
            # 版本号通常以数字开头
            if part and part[0].isdigit():
                package_name = '-'.join(parts[:i])
                
                # 验证包名是否符合PEP 427规范
                # 包名只能包含字母、数字、下划线、点和连字符
                # 不能以连字符开头或结尾，不能有连续连字符
                if self._is_valid_package_name(package_name):
                    return package_name
                else:
                    # 如果包名不符合规范，尝试清理
                    cleaned_name = self._clean_package_name(package_name)
                    self.logger.warning(f"包名 '{package_name}' 不符合规范，使用清理后的名称: '{cleaned_name}'")
                    return cleaned_name
        
        # 如果找不到版本号，返回第一个部分
        return parts[0] if parts else "unknown"

    def _force_rename_whl_file(self, whl_path: Path, original_filename: str) -> Optional[Path]:
        """
        强制重命名WHL文件，根据包内信息生成符合PEP 427规范的文件名
        
        Args:
            whl_path: WHL文件路径
            original_filename: 原始文件名
            
        Returns:
            Optional[Path]: 重命名后的文件路径，如果失败返回None
        """
        try:
            # 从WHL文件中提取包信息
            package_info = self._extract_package_info_from_whl(whl_path)
            
            if package_info and 'name' in package_info and 'version' in package_info:
                # 使用从WHL文件中提取的真实包名和版本
                package_name = package_info['name']
                version = package_info['version']
                
                # 验证包名是否符合PEP 427规范
                if not self._is_valid_package_name(package_name):
                    self.logger.warning(f"包名 '{package_name}' 不符合PEP 427规范，进行清理")
                    package_name = self._clean_package_name(package_name)
                    self.logger.info(f"清理后的包名: {package_name}")
                
                # 生成符合PEP 427规范的文件名
                new_filename = self._generate_whl_filename(package_name, version)
                new_path = whl_path.parent / new_filename
                
                self.logger.info(f"执行强制重命名: {original_filename} -> {new_filename}")
                
                # 重命名文件
                whl_path.rename(new_path)
                self.logger.info(f"✅ 文件重命名成功: {new_filename}")
                
                return new_path
            else:
                # 如果无法提取包信息，使用备用方案
                self.logger.warning(f"无法从WHL文件中提取包信息，使用备用重命名方案")
                
                # 从原始文件名提取包名
                package_name = self._extract_package_name(original_filename)
                
                # 验证并清理包名
                if not self._is_valid_package_name(package_name):
                    package_name = self._clean_package_name(package_name)
                    self.logger.info(f"备用方案清理后的包名: {package_name}")
                
                # 生成符合PEP 427规范的备用文件名
                new_filename = self._generate_whl_filename(package_name, "0.0.1")
                new_path = whl_path.parent / new_filename
                
                self.logger.info(f"执行备用重命名: {original_filename} -> {new_filename}")
                
                # 重命名文件
                whl_path.rename(new_path)
                self.logger.info(f"✅ 文件重命名成功: {new_filename}")
                
                return new_path
                
        except Exception as e:
            self.logger.error(f"强制重命名WHL文件失败: {e}")
            return None
    
    def _is_valid_package_name(self, package_name: str) -> bool:
        """
        验证包名是否符合PEP 427规范
        
        Args:
            package_name: 包名
            
        Returns:
            bool: 是否有效
        """
        # 包名不能为空
        if not package_name:
            return False
        
        # 不能以连字符开头或结尾
        if package_name.startswith('-') or package_name.endswith('-'):
            return False
        
        # 不能有连续连字符
        if '--' in package_name:
            return False
        
        # 只能包含字母、数字、下划线、点和连字符
        if not re.match(r'^[a-zA-Z0-9._-]+$', package_name):
            return False
        
        return True
    
    def _clean_package_name(self, package_name: str) -> str:
        """
        清理包名使其符合PEP 427规范
        
        Args:
            package_name: 包名
            
        Returns:
            str: 清理后的包名
        """
        # 移除开头和结尾的连字符
        cleaned = package_name.strip('-') 
        
        # 替换连续连字符为单个连字符
        cleaned = re.sub(r'-+', '-', cleaned)
        
        # 只保留字母、数字、下划线、点和连字符
        cleaned = re.sub(r'[^a-zA-Z0-9._-]', '', cleaned)
        
        # 再次确保不以连字符开头或结尾
        cleaned = cleaned.strip('-')
        
        # 如果清理后为空，返回默认名称
        if not cleaned:
            return "unknown_package"
        
        return cleaned
    
    def _generate_whl_filename(self, package_name: str, package_version: str) -> str:
        """
        生成符合PEP 427规范的WHL文件名
        
        Args:
            package_name: 包名
            package_version: 包版本
            
        Returns:
            str: 生成的WHL文件名
        """
        # 生成标准WHL文件名格式: {package}-{version}-py3-none-any.whl
        # 注意：pip的正则表达式 [^\\-]+ 要求包名不能包含连字符
        # 将包名中的连字符转换为下划线，以确保pip能够正确解析
        clean_name = package_name.replace('-', '_')
        return f"{clean_name}-{package_version}-py3-none-any.whl"
    
    def _validate_whl_integrity(self, whl_path: Path) -> bool:
        """
        验证WHL文件完整性
        
        Args:
            whl_path: WHL文件路径
            
        Returns:
            bool: 文件是否完整有效
        """
        try:
            if not whl_path.exists():
                self.logger.error(f"WHL文件不存在: {whl_path}")
                return False
            
            # 检查文件大小
            file_size = whl_path.stat().st_size
            if file_size < 100:  # WHL文件通常至少几百字节
                self.logger.error(f"WHL文件大小异常: {file_size} bytes")
                return False
            
            # 检查是否为有效的ZIP文件
            import zipfile
            try:
                with zipfile.ZipFile(whl_path, 'r') as whl_zip:
                    # 检查ZIP文件是否损坏
                    if whl_zip.testzip() is not None:
                        self.logger.error("WHL文件ZIP结构损坏")
                        return False
                    
                    # 检查是否包含必要的文件结构
                    file_list = whl_zip.namelist()
                    
                    # 检查是否包含.dist-info目录
                    dist_info_files = [f for f in file_list if '.dist-info' in f]
                    if not dist_info_files:
                        self.logger.error("WHL文件缺少.dist-info目录")
                        return False
                    
                    # 提取.dist-info目录路径
                    dist_info_dirs = set()
                    for file_path in dist_info_files:
                        # 提取目录部分，例如：executionkit-0.0.2.dist-info/
                        dir_path = file_path.split('/')[0] + '/' if '/' in file_path else file_path.split('\\')[0] + '\\'
                        dist_info_dirs.add(dir_path)
                    
                    # 检查是否包含METADATA文件
                    metadata_found = False
                    for dist_dir in dist_info_dirs:
                        metadata_file = dist_dir + "METADATA"
                        if metadata_file in file_list:
                            # 验证METADATA文件内容
                            with whl_zip.open(metadata_file) as f:
                                metadata_content = f.read().decode('utf-8', errors='ignore')
                                if 'Name:' not in metadata_content or 'Version:' not in metadata_content:
                                    self.logger.error("METADATA文件内容不完整")
                                    return False
                            metadata_found = True
                            break
                    
                    if not metadata_found:
                        self.logger.error("WHL文件缺少METADATA文件")
                        return False
                    
                    # 检查是否包含包目录
                    package_files = [f for f in file_list if '.dist-info' not in f and '__pycache__' not in f and not f.endswith('/')]
                    if not package_files:
                        self.logger.error("WHL文件缺少包文件")
                        return False
                    
                    self.logger.debug(f"WHL文件结构验证通过: {len(file_list)} 个文件")
                    return True
                    
            except zipfile.BadZipFile:
                self.logger.error("WHL文件不是有效的ZIP格式")
                return False
            except Exception as e:
                self.logger.error(f"验证WHL文件完整性时发生错误: {e}")
                return False
                
        except Exception as e:
            self.logger.error(f"验证WHL文件完整性失败: {e}")
            return False
    
    def _format_size(self, size_bytes: int) -> str:
        """格式化文件大小显示"""
        if size_bytes == 0:
            return "0B"
        size_names = ["B", "KB", "MB", "GB"]
        i = 0
        while size_bytes >= 1024 and i < len(size_names) - 1:
            size_bytes /= 1024.0
            i += 1
        return f"{size_bytes:.1f} {size_names[i]}"
    
    def _cleanup_temp_files(self):
        """清理临时文件"""
        try:
            if self.temp_dir.exists():
                # 保留备份文件，删除其他临时文件
                for item in self.temp_dir.iterdir():
                    if not item.name.endswith('_backup.txt'):
                        if item.is_file():
                            item.unlink()
                        else:
                            shutil.rmtree(item)
                
                self.logger.debug("临时文件清理完成")
        except Exception as e:
            self.logger.warning(f"清理临时文件时发生错误: {e}")
    
    async def update_from_whl(self, whl_url: str) -> bool:
        """
        根据whl包URL进行覆盖更新
        
        Args:
            whl_url: whl包下载URL
            version: 版本号
            
        Returns:
            bool: 更新是否成功
        """
        self.logger.info(f"开始WHL包更新流程，URL: {whl_url}")
        
        # 验证Python环境
        python_path = self._get_python_executable()
        if not python_path:
            self.logger.error("无法获取有效的Python环境，更新失败")
            return False
        
        # 下载whl包
        whl_path = await self._download_whl_file(whl_url)
        if not whl_path:
            self.logger.error("whl包下载失败")
            return False
        
        # 提取包名称
        package_name = self._extract_package_name(whl_path.name)
        self.logger.info(f"检测到包名称: {package_name}")
        
        # 创建备份
        backup_created = self._create_backup(package_name)
        if not backup_created:
            self.logger.warning("备份创建失败，继续执行更新")
        
        # 执行安装
        success = False
        error_msg = ""
        
        for attempt in range(self.max_retries):
            self.logger.info(f"尝试安装 (第 {attempt + 1}/{self.max_retries} 次)")
            
            success, error_msg = self._install_whl_package(whl_path, python_path)
            
            if success:
                break
            else:
                if attempt < self.max_retries - 1:
                    wait_time = 2 ** attempt  # 指数退避
                    self.logger.info(f"安装失败，等待 {wait_time}秒后重试...")
                    time.sleep(wait_time)
        
        # 处理安装结果
        if success:
            self.logger.info("WHL包更新成功")
            # 清理临时文件（保留备份）
            self._cleanup_temp_files()
            return True
        else:
            self.logger.error(f"WHL包更新失败: {error_msg}")
            
            # 尝试回滚
            if backup_created:
                self.logger.info("开始回滚到备份版本")
                rollback_success = self._rollback_package(package_name)
                if rollback_success:
                    self.logger.info("回滚成功")
                else:
                    self.logger.error("回滚失败")
            
            return False


def update_from_whl_sync(whl_url: str) -> dict:
    """
    便捷函数：根据whl包URL进行覆盖更新（同步接口）
    
    Args:
        whl_url: whl包下载URL
        
    Returns:
        dict: 更新结果，包含success和error字段
    """
    updater = WhlUpdater()
    
    # 同步版本的更新逻辑
    logger = get_logger()
    logger.info(f"开始同步WHL包更新流程，URL: {whl_url}")
    
    # 验证Python环境
    python_path = updater._get_python_executable()
    if not python_path:
        logger.error("无法获取有效的Python环境，更新失败")
        return {"success": False, "error": "无法获取有效的Python环境"}
    
    # 使用项目统一的同步文件下载器
    from pathlib import Path
    import tempfile
    
    try:
        # 从URL提取文件名
        whl_filename = whl_url.split('/')[-1]
        if not whl_filename.endswith('.whl'):
            logger.error(f"URL格式错误，不是有效的whl文件: {whl_url}")
            return {"success": False, "error": f"URL格式错误，不是有效的whl文件: {whl_url}"}
        
        whl_path = updater.temp_dir / whl_filename
        
        # 使用同步版本的下载器
        from .file_downloader import download_file_sync
        download_success = download_file_sync(whl_url, str(whl_path))
        
        if not download_success:
            logger.error("WHL包下载失败")
            return {"success": False, "error": "WHL包下载失败"}
        
        logger.info(f"WHL包下载完成: {whl_path}")
        
        # 下载完成后，进行WHL文件完整性验证和重命名检查
        original_filename = whl_path.name
        logger.info(f"下载完成，原始文件名: {original_filename}")
        
        # 验证WHL文件完整性
        if not updater._validate_whl_integrity(whl_path):
            logger.error("❌ WHL文件完整性验证失败，可能文件损坏或不完整")
            # 删除损坏的文件
            try:
                whl_path.unlink()
                logger.info("已删除损坏的WHL文件")
            except Exception as e:
                logger.error(f"删除损坏文件失败: {e}")
            return {"success": False, "error": "WHL文件完整性验证失败，可能文件损坏或不完整"}
        
        logger.info("✅ WHL文件完整性验证通过")
        
        # 强制根据WHL包内部信息进行重命名（硬性执行标准）
        logger.info(f"原始文件名: {original_filename}")
        
        # 从WHL文件中读取包信息进行重命名
        package_info = updater._extract_package_info_from_whl(whl_path)
        if package_info and package_info.get('name') and package_info.get('version'):
            package_name = package_info['name']
            package_version = package_info['version']
            
            # 验证包名是否符合PEP 427规范
            if not updater._is_valid_package_name(package_name):
                logger.warning(f"包名 '{package_name}' 不符合PEP 427规范，进行清理")
                package_name = updater._clean_package_name(package_name)
                logger.info(f"清理后的包名: {package_name}")
            
            # 生成符合PEP 427规范的文件名
            new_filename = updater._generate_whl_filename(package_name, package_version)
            new_whl_path = updater.temp_dir / new_filename
            
            logger.info(f"从WHL文件中提取包信息: {package_name} {package_version}")
            logger.info(f"执行强制重命名: {original_filename} -> {new_filename}")
            
            # 检查目标文件是否已存在
            if new_whl_path.exists():
                logger.warning(f"目标文件已存在: {new_whl_path}")
                # 删除已存在的文件
                try:
                    new_whl_path.unlink()
                    logger.info("已删除已存在的文件")
                except Exception as e:
                    logger.error(f"删除已存在文件失败: {e}")
            
            # 执行重命名
            try:
                whl_path.rename(new_whl_path)
                logger.info(f"✅ 文件重命名成功: {new_filename}")
                whl_path = new_whl_path
            except Exception as rename_error:
                logger.error(f"❌ 文件重命名失败: {rename_error}")
                # 记录详细的错误信息以便调试
                logger.debug(f"重命名失败详情: 源文件={whl_path}, 目标文件={new_whl_path}")
        else:
            logger.warning("⚠️ 无法从WHL文件中提取包信息，使用原始文件名")
        
        # 记录最终文件名
        final_filename = whl_path.name
        logger.info(f"最终文件名: {final_filename}")
        
        # 提取包名称
        package_name = updater._extract_package_name(whl_path.name)
        logger.info(f"检测到包名称: {package_name}")
        
        # 创建备份
        backup_created = updater._create_backup(package_name)
        if not backup_created:
            logger.warning("备份创建失败，继续执行更新")
        
        # 执行安装
        success = False
        error_msg = ""
        
        for attempt in range(updater.max_retries):
            logger.info(f"尝试安装 (第 {attempt + 1}/{updater.max_retries} 次)")
            
            success, error_msg = updater._install_whl_package(whl_path, python_path)
            
            if success:
                break
            else:
                if attempt < updater.max_retries - 1:
                    wait_time = 2 ** attempt  # 指数退避
                    logger.info(f"安装失败，等待 {wait_time}秒后重试...")
                    import time
                    time.sleep(wait_time)
        
        # 处理安装结果
        if success:
            logger.info("WHL包更新成功")
            # 清理临时文件（保留备份）
            updater._cleanup_temp_files()
            return {"success": True, "error": ""}
        else:
            logger.error(f"WHL包更新失败: {error_msg}")
            
            # 尝试回滚
            if backup_created:
                logger.info("开始回滚到备份版本")
                rollback_success = updater._rollback_package(package_name)
                if rollback_success:
                    logger.info("回滚成功")
                else:
                    logger.error("回滚失败")
            
            return {"success": False, "error": error_msg}
            
    except Exception as e:
        logger.error(f"同步WHL包更新过程中发生错误: {e}")
        return {"success": False, "error": str(e)}


def update_from_whl(whl_url: str) -> bool:
    """
    便捷函数：根据whl包URL进行覆盖更新（异步接口，兼容旧版本）
    
    Args:
        whl_url: whl包下载URL
        
    Returns:
        bool: 更新是否成功
    """
    import asyncio
    updater = WhlUpdater()
    return asyncio.run(updater.update_from_whl(whl_url))


def main():
    """命令行入口"""
    logger = get_logger()
    
    if len(sys.argv) != 2:
        logger.error("用法: python whl_updater.py <whl包URL>")
        logger.error("示例: python whl_updater.py https://example.com/package-1.0.0-py3-none-any.whl")
        sys.exit(1)
    
    whl_url = sys.argv[1]
    
    logger.info("WHL包更新工具启动")
    logger.info(f"目标URL: {whl_url}")
    logger.info("-" * 50)
    
    # 执行更新
    success = update_from_whl(whl_url)
    
    if success:
        logger.info("WHL包更新成功！")
        sys.exit(0)
    else:
        logger.error("WHL包更新失败！")
        sys.exit(1)


if __name__ == "__main__":
    main()