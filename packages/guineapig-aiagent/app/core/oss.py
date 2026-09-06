import io
import json
import os
import random
import time
from io import BytesIO

import boto3
import requests
from botocore.exceptions import ClientError
from app.config import settings
from app.core.log import logger

# 从配置中获取OSS配置信息
OSS_AK = settings.OSS_AK
OSS_SK = settings.OSS_SK
OSS_ENDPOINT = settings.OSS_ENDPOINT
OSS_BUCKET = settings.OSS_BUCKET
OSS_IS_ADDRESSING_STYLE = settings.OSS_IS_ADDRESSING_STYLE


class OSS:
    def __init__(
        self, ak=OSS_AK, sk=OSS_SK, endpoint=OSS_ENDPOINT, bucket=OSS_BUCKET, region="", is_addressing_style=OSS_IS_ADDRESSING_STYLE
    ):
        self.AK = ak
        self.SK = sk
        self.endpoint = endpoint  # 修正拼写错误
        self.region = region
        self.bucket_name = bucket
        self.is_addressing_style = is_addressing_style
        self.init_client(self.AK, self.SK, self.endpoint, self.region, self.is_addressing_style)

    def init_client(self, AK, SK, endpoint, region, is_addressing_style=OSS_IS_ADDRESSING_STYLE):
        """初始化OSS客户端
        
        Args:
            AK: 访问密钥ID
            SK: 秘密访问密钥
            endpoint: OSS端点URL
            region: 区域
            is_addressing_style: 是否使用路径寻址模式（兼容天翼云），默认为False
        """
        try:
            from botocore.config import Config

            # 根据参数选择不同的配置方式
            if is_addressing_style:
                # 使用路径寻址模式（兼容天翼云）
                config = Config(
                    retries={"max_attempts": 3},
                    signature_version="s3",  # 使用签名版本2（兼容性更好）
                    s3={
                        "addressing_style": "path",  # 路径寻址模式（兼容天翼云）
                    },
                )
                self.s3_client = boto3.client(
                    "s3",
                    aws_access_key_id=AK,
                    aws_secret_access_key=SK,
                    endpoint_url=endpoint,
                    config=config,
                    verify=True,
                )
                logger.info("使用路径寻址模式配置OSS客户端")
            else:
                # 默认配置（连接池优化）
                config = Config(
                    max_pool_connections=50,  # 增加连接池大小
                    retries={"max_attempts": 3, "mode": "standard"},
                )
                self.s3_client = boto3.client(
                    "s3",
                    aws_access_key_id=AK,
                    aws_secret_access_key=SK,
                    endpoint_url=endpoint,
                    region_name=region,
                    use_ssl=False,
                    config=config,
                )
                logger.info("使用默认连接池优化配置OSS客户端")


            # 测试连接
            # self.s3_client.head_bucket(Bucket=self.bucket_name)
            # logger.info(f"成功连接到OSS桶: {self.bucket_name}")
        except ClientError as e:
            logger.error(f"初始化OSS客户端失败: {e}")
            if e.response["Error"]["Code"] == "403":
                logger.error("权限不足，无法访问该桶")
            elif e.response["Error"]["Code"] == "404":
                logger.error("指定的桶不存在")
            raise  # 重新抛出异常，让调用者处理

    def _download_single(self, remote_path, disk_path, chunk_size=1024 * 64):
        """下载单个文件到磁盘。失败时（ClientError/IOError）直接向上抛出，不静默吞掉。"""
        resp = self.s3_client.get_object(Bucket=self.bucket_name, Key=remote_path)
        content_length = resp["ContentLength"]
        body = resp["Body"]
        with open(disk_path, "wb") as f:
            logger.info(f"Downloading {remote_path} ... ({content_length} bytes)")
            for chunk in body.iter_chunks(chunk_size):
                f.write(chunk)

    def download_object_as_bytesIO(self, remote_path: str, chunk_size: int = 1024 * 64) -> BytesIO:
        """从对象存储下载文件并返回BytesIO对象
        
        Args:
            remote_path: 远程文件路径
            chunk_size: 分块大小，默认64KB
            
        Returns:
            BytesIO: 文件内容的BytesIO对象
        """
        try:
            resp = self.s3_client.get_object(Bucket=self.bucket_name, Key=remote_path)
            body = resp["Body"]
            
            # 创建BytesIO对象
            bytes_io = BytesIO()
            
            for chunk in body.iter_chunks(chunk_size):
                bytes_io.write(chunk)
            
            # 重置指针到开头以便后续读取
            bytes_io.seek(0)
            return bytes_io
            
        except ClientError as e:
            logger.error(
                f"从 {remote_path} 下载对象（路径）为BytesIO失败: {e}，尝试直接用link方式下载"
            )
            try:
                return self.download_doc_from_http(remote_path)
            except Exception as e:
                logger.error(f"尝试直接用link方式下载失败: {e}")
                raise

    def download_doc_from_http(self, url: str, timeout: int = 30) -> BytesIO:
        """
        从对象存储地址下载文件并返回BytesIO对象
        Args:
            url (str): 文件的HTTP地址
            timeout (int): 请求超时时间，默认30秒

        Returns:
            BytesIO: 文件内容的BytesIO对象
        """
        try:
            response = requests.get(url, timeout=timeout)
            response.raise_for_status()

            # 使用BytesIO将文件内容转换为文件类对象
            doc = BytesIO(response.content)
            return doc
        except requests.RequestException as e:
            raise requests.RequestException(
                f"Failed to fetch file from {url}: {str(e)}"
            )
        except Exception as e:
            raise Exception(f"Failed to parse file: {str(e)}")

    def download_oss(self, remote_path, disk_path, num=-1):
        if not remote_path.endswith("/"):
            disk_path = os.path.join(disk_path, os.path.basename(remote_path))
            self._download_single(remote_path, disk_path)
        else:
            pre_dir = os.path.split(remote_path[:-1])[0]
            objects = self.list_objects(remote_path)
            if num < 0:
                num = len(objects)
            if len(objects) < num:
                num = len(objects)
            objects = random.sample(objects, num)
            for obj in objects:
                remo_disk_dir = obj["Key"].replace(pre_dir, "", 1)
                if remo_disk_dir.startswith("/"):
                    remo_disk_dir = remo_disk_dir[1:]
                disk_name = os.path.join(disk_path, remo_disk_dir)
                disk_dir = os.path.split(disk_name)[0]
                if os.path.exists(disk_name):
                    logger.info(f"{disk_name} exists, skip downloading.")
                    continue
                if (not os.path.exists(disk_dir)) and disk_dir:
                    os.makedirs(disk_dir, exist_ok=True)
                if not obj["Key"].endswith("/"):
                    self._download_single(obj["Key"], disk_name)

    def _upload_single(self, file_obj_or_path, remote_path):
        """上传单个文件到OSS，支持大文件分块上传
        
        Args:
            file_obj_or_path: 文件路径（字符串）或文件对象（如BytesIO、BufferedReader等）
            remote_path: 远程路径
            
        Returns:
            bool: 上传是否成功
        """
        try:
            # 检查是否为文件路径（字符串）
            if isinstance(file_obj_or_path, str):
                # 检查文件是否存在
                if not os.path.exists(file_obj_or_path):
                    logger.error(f"文件不存在: {file_obj_or_path}")
                    return False
                
                logger.info(f"正在上传文件: {file_obj_or_path} -> {self.bucket_name}/{remote_path}")
                file_size = os.path.getsize(file_obj_or_path)
                
                # 根据文件大小选择上传方式
                if file_size > 8 * 1024 * 1024:  # 大于8MB使用分块上传
                    return self._upload_large_file(file_obj_or_path, remote_path, file_size)
                else:
                    return self._upload_small_file(file_obj_or_path, remote_path)
                    
            else:  # 文件对象（如BytesIO、BufferedReader等）
                logger.info(f"正在上传文件对象到 {self.bucket_name}/{remote_path}")
                
                # 重置文件指针到开头（如果支持seek操作）
                if hasattr(file_obj_or_path, 'seek'):
                    file_obj_or_path.seek(0)
                
                # 对于文件对象，尝试获取大小
                try:
                    # 优先使用getbuffer()方法获取大小（适用于BytesIO）
                    if hasattr(file_obj_or_path, 'getbuffer'):
                        file_size = len(file_obj_or_path.getbuffer())
                    # 其次使用getvalue()方法
                    elif hasattr(file_obj_or_path, 'getvalue'):
                        file_size = len(file_obj_or_path.getvalue())
                    # 最后尝试使用tell()和seek()组合
                    elif hasattr(file_obj_or_path, 'tell') and hasattr(file_obj_or_path, 'seek'):
                        current_pos = file_obj_or_path.tell()
                        file_obj_or_path.seek(0, 2)  # 移动到文件末尾
                        file_size = file_obj_or_path.tell()
                        file_obj_or_path.seek(current_pos)  # 恢复原位置
                    else:
                        file_size = None
                    
                    # 重置文件指针到开头
                    if hasattr(file_obj_or_path, 'seek'):
                        file_obj_or_path.seek(0)
                    
                    # 根据文件大小选择上传方式
                    if file_size and file_size > 8 * 1024 * 1024:  # 大于8MB使用分块上传
                        return self._upload_large_file_obj(file_obj_or_path, remote_path, file_size)
                    else:
                        return self._upload_small_file_obj(file_obj_or_path, remote_path)
                        
                except (AttributeError, TypeError, OSError) as e:
                    logger.warning(f"无法获取文件对象大小，使用标准上传: {str(e)}")
                    # 如果无法获取大小，使用标准上传
                    return self._upload_small_file_obj(file_obj_or_path, remote_path)
                    
        except Exception as e:
            logger.error(f"文件上传失败 {remote_path}: {str(e)}")
            if isinstance(e, ClientError):
                error_code = e.response.get("Error", {}).get("Code", "Unknown")
                error_message = e.response.get("Error", {}).get("Message", "Unknown error")
                logger.error(f"OSS错误 - 代码: {error_code}, 消息: {error_message}")
                
                # 常见错误类型处理
                if error_code == "403":
                    logger.error("上传失败: 权限不足")
                elif error_code == "NoSuchBucket":
                    logger.error("上传失败: 存储桶不存在")
                elif error_code == "AccessDenied":
                    logger.error("上传失败: 访问被拒绝")
            return False
    def create_folder(self, folder_path):
        """在OSS桶中创建文件夹"""
        if not folder_path.endswith("/"):
            folder_path += "/"

        try:
            self.s3_client.put_object(
                Bucket=self.bucket_name, Key=folder_path
            )
            logger.info(f"文件夹创建成功: '{folder_path}'")
            return True
        except ClientError as e:
            logger.error(f"创建文件夹失败: {e}")
            if e.response["Error"]["Code"] == "403":
                logger.error("创建文件夹失败: 权限不足")
            return False

    def delete_folder(self, folder_path):
        """删除OSS桶中的文件夹及其所有内容"""
        if not folder_path.endswith("/"):
            folder_path += "/"

        try:
            # 列出文件夹下的所有对象
            objects = []
            continuation_token = None

            # 处理分页情况
            while True:
                list_kwargs = {
                    "Bucket": self.bucket_name,
                    "Prefix": folder_path,
                    "MaxKeys": 1000,
                }
                if continuation_token:
                    list_kwargs["ContinuationToken"] = continuation_token

                response = self.s3_client.list_objects_v2(**list_kwargs)

                if "Contents" in response:
                    objects.extend(
                        [{"Key": obj["Key"]} for obj in response["Contents"]]
                    )

                if not response.get("IsTruncated"):
                    break

                continuation_token = response.get("NextContinuationToken")

            # 检查文件夹是否为空
            if objects:
                raise ValueError(f"文件夹 '{folder_path}' 不为空，无法删除。请先清空文件夹内容。")

            # 批量删除对象
            if objects:
                # 分批删除，每次最多删除1000个对象
                for i in range(0, len(objects), 1000):
                    batch = objects[i : i + 1000]
                    self.s3_client.delete_objects(
                        Bucket=self.bucket_name,
                        Delete={"Objects": batch},
                    )
                logger.info(f"已删除文件夹 '{folder_path}' 中的 {len(objects)} 个对象")

            logger.info(f"文件夹 '{folder_path}' 已成功删除")
            return True
        except ClientError as e:
            logger.error(f"删除文件夹失败: {e}")
            if e.response["Error"]["Code"] == "403":
                logger.error(
                    "删除文件夹失败: 权限不足，请检查是否拥有s3:ListBucket和s3:DeleteObject权限"
                )
            return False

    def list_objects(self, prefix, suffix=None):
        """列出指定前缀下的所有对象

        Args:
            prefix: 对象前缀，用于过滤对象
            suffix: 可选，对象后缀，用于进一步过滤对象

        Returns:
            list: 对象列表，每个对象包含Key和其他元数据
        """
        objects = []
        continuation_token = None

        try:
            while True:
                list_kwargs = {
                    "Bucket": self.bucket_name,
                    "Prefix": prefix,
                    "MaxKeys": 1000,
                }
                if continuation_token:
                    list_kwargs["ContinuationToken"] = continuation_token

                response = self.s3_client.list_objects_v2(**list_kwargs)

                if "Contents" in response:
                    for obj in response["Contents"]:
                        if suffix is None or obj["Key"].endswith(suffix):
                            objects.append(obj)

                if not response.get("IsTruncated"):
                    break

                continuation_token = response.get("NextContinuationToken")

            logger.info(f"找到 {len(objects)} 个对象，前缀: {prefix}")
            return objects
        except ClientError as e:
            logger.error(f"列出对象失败: {e}")
            if e.response["Error"]["Code"] == "403":
                logger.error("列出对象失败: 权限不足，请检查是否拥有s3:ListBucket权限")
            raise

    def folder_exists(self, folder_path):
        """检查桶中是否存在指定文件夹"""
        if not folder_path.endswith("/"):
            folder_path += "/"

        try:
            response = self.s3_client.list_objects_v2(
                Bucket=self.bucket_name, Prefix=folder_path, MaxKeys=1
            )
            return "Contents" in response or "CommonPrefixes" in response
        except ClientError as e:
            logger.error(f"检查文件夹存在性失败: {e}")
            if e.response["Error"]["Code"] == "403":
                logger.error(
                    "检查文件夹失败: 权限不足，请检查是否拥有s3:ListBucket权限"
                )
            return False

    def get_object_url(self, object_name, expires=3600 * 24 * 7):
        result_url = self.s3_client.generate_presigned_url(
            "get_object",
            Params={"Bucket": self.bucket_name, "Key": object_name},
            ExpiresIn=expires,
        )
        return result_url

    def upload_doc_to_s3_and_get_path(
        self, file_obj_or_path, project_id, file_path, filename=None
    ):
        """上传文件到OSS并返回远程路径

        Args:
            file_obj_or_path: 文件路径（字符串）或文件对象（如BytesIO）
            project_id: 项目ID
            file_path: 文件路径. 在这个实现中, 它代表 record_id.
            filename: 可选，当传入文件对象时，用于指定文件名

        Returns:
            str: 远程路径 (remote_path)
        """
        # 确定远程文件名
        if isinstance(file_obj_or_path, str):
            # 如果是文件路径，使用原文件名
            if filename:
                remote_filename = filename
            else:
                remote_filename = os.path.basename(file_obj_or_path)
        else:
            # 如果是文件对象，使用提供的文件名或默认名
            if filename:
                remote_filename = filename
            else:
                remote_filename = "uploaded_file.docx"

        # 构建最终的 remote_path: project_id/record_id/filename
        final_path = f"{project_id}/{file_path}"
        remote_path = f"{final_path}/{remote_filename}"

        max_attempts = 3
        for attempt in range(1, max_attempts + 1):
            try:
                self._upload_single(file_obj_or_path, remote_path)
                logger.info(f"文件上传成功，远程路径: {remote_path}")
                return remote_path
            except Exception as e:
                if attempt < max_attempts:
                    logger.warning(f"第{attempt}次上传文件到OSS失败，将重试: {e}")
                    time.sleep(1)
                else:
                    logger.error(f"上传文件到OSS失败: {e}")
                    raise

    def list_folders_recursive(self, prefix=""):
        """递归获取指定前缀下的所有文件夹列表
        
        Args:
            prefix: 目录前缀，为空则从根目录开始
            
        Returns:
            list: 文件夹路径列表（包含完整路径）
        """
        folders = set()
        continuation_token = None
        
        try:
            while True:
                list_kwargs = {
                    "Bucket": self.bucket_name,
                    "Prefix": prefix,
                    "Delimiter": "/",
                    "MaxKeys": 1000,
                }
                if continuation_token:
                    list_kwargs["ContinuationToken"] = continuation_token
                
                response = self.s3_client.list_objects_v2(**list_kwargs)
                
                # 处理当前层级的文件夹
                if "CommonPrefixes" in response:
                    for common_prefix in response["CommonPrefixes"]:
                        folder_path = common_prefix["Prefix"]
                        folders.add(folder_path)
                        # 递归获取子文件夹
                        sub_folders = self.list_folders_recursive(folder_path)
                        folders.update(sub_folders)
                
                # 处理分页
                if not response.get("IsTruncated"):
                    break
                    
                continuation_token = response.get("NextContinuationToken")
            
            logger.info(f"找到 {len(folders)} 个文件夹，前缀: {prefix}")
            return sorted(list(folders))
            
        except ClientError as e:
            logger.error(f"递归列出文件夹失败: {e}")
            if e.response["Error"]["Code"] == "403":
                logger.error("列出文件夹失败: 权限不足，请检查是否拥有s3:ListBucket权限")
            raise

    def upload_file(self, file_obj_or_path, remote_path, max_attempts=3):
        """上传文件的公共方法，包装 _upload_single 方法
        
        Args:
            file_obj_or_path: 文件路径（字符串）或文件对象（如BytesIO）
            remote_path: 远程路径
            max_attempts: 最大重试次数，默认3次
            
        Returns:
            bool: 上传是否成功
        """
        for attempt in range(1, max_attempts + 1):
            try:
                self._upload_single(file_obj_or_path, remote_path)
                logger.info(f"文件上传成功，远程路径: {remote_path}")
                return True
            except Exception as e:
                if attempt < max_attempts:
                    logger.warning(f"第{attempt}次上传文件到OSS失败，将重试: {e}")
                    time.sleep(1)
                else:
                    logger.error(f"上传文件到OSS失败: {e}")
                    return False
        return None

    def _upload_small_file(self, local_file_path, remote_path):
        """上传小文件（小于8MB）"""
        try:
            # 使用标准上传方法（参考oss_utils_upload_upsertsfile.py）
            with open(local_file_path, "rb") as file_data:
                self.s3_client.put_object(
                    Bucket=self.bucket_name,
                    Key=remote_path,
                    Body=file_data.read(),
                    ContentType="application/octet-stream",
                )
            logger.info(f"小文件上传成功: {local_file_path} -> {self.bucket_name}/{remote_path}")
            return True
        except Exception as e:
            logger.error(f"小文件上传失败 {local_file_path}: {str(e)}")
            return False

    def _upload_small_file_obj(self, file_obj, remote_path):
        """上传小文件对象（小于8MB）"""
        try:
            # 重置文件指针到开头
            if hasattr(file_obj, 'seek'):
                file_obj.seek(0)
            
            # 使用put_object方法上传文件对象内容
            self.s3_client.put_object(
                Bucket=self.bucket_name,
                Key=remote_path,
                Body=file_obj.read() if hasattr(file_obj, 'read') else file_obj,
                ContentType="application/octet-stream",
            )
            logger.info(f"小文件对象上传成功: {self.bucket_name}/{remote_path}")
            return True
        except Exception as e:
            logger.error(f"小文件对象上传失败 {remote_path}: {str(e)}")
            return False

    def _upload_large_file(self, local_file_path, remote_path, file_size):
        """上传大文件（大于8MB），使用分块上传"""
        try:
            return self._upload_with_multipart(local_file_path, remote_path, file_size)
        except Exception as e:
            logger.error(f"大文件上传失败 {local_file_path}: {str(e)}")
            return False

    def _upload_large_file_obj(self, file_obj, remote_path, file_size):
        """上传大文件对象（大于8MB），使用分块上传"""
        try:
            return self._upload_with_multipart_obj(file_obj, remote_path, file_size)
        except Exception as e:
            logger.error(f"大文件对象上传失败 {remote_path}: {str(e)}")
            return False

    def _upload_with_multipart(self, local_file_path, remote_path, file_size):
        """使用分块上传大文件"""
        upload_id = None
        try:
            # 创建分块上传
            response = self.s3_client.create_multipart_upload(
                Bucket=self.bucket_name, Key=remote_path
            )
            upload_id = response["UploadId"]

            # 分块大小设置为5MB
            part_size = 5 * 1024 * 1024
            parts = []

            with open(local_file_path, "rb") as file_data:
                part_number = 1
                while True:
                    chunk = file_data.read(part_size)
                    if not chunk:
                        break

                    # 上传分块
                    response = self.s3_client.upload_part(
                        Bucket=self.bucket_name,
                        Key=remote_path,
                        PartNumber=part_number,
                        UploadId=upload_id,
                        Body=chunk,
                    )
                    parts.append({"PartNumber": part_number, "ETag": response["ETag"]})
                    part_number += 1

            # 完成分块上传
            self.s3_client.complete_multipart_upload(
                Bucket=self.bucket_name,
                Key=remote_path,
                UploadId=upload_id,
                MultipartUpload={"Parts": parts},
            )

            logger.info(
                f"大文件分块上传成功: {local_file_path} -> {self.bucket_name}/{remote_path}"
            )
            return True

        except Exception as e:
            logger.error(f"大文件分块上传失败 {local_file_path}: {str(e)}")
            # 如果出错，中止分块上传
            if upload_id:
                try:
                    self.s3_client.abort_multipart_upload(
                        Bucket=self.bucket_name, Key=remote_path, UploadId=upload_id
                    )
                except:
                    pass
            return False

    def _upload_with_multipart_obj(self, file_obj, remote_path, file_size):
        """使用分块上传大文件对象"""
        upload_id = None
        try:
            # 创建分块上传
            response = self.s3_client.create_multipart_upload(
                Bucket=self.bucket_name, Key=remote_path
            )
            upload_id = response["UploadId"]

            # 分块大小设置为5MB
            part_size = 5 * 1024 * 1024
            parts = []

            file_obj.seek(0)
            part_number = 1
            while True:
                chunk = file_obj.read(part_size)
                if not chunk:
                    break

                # 上传分块
                response = self.s3_client.upload_part(
                    Bucket=self.bucket_name,
                    Key=remote_path,
                    PartNumber=part_number,
                    UploadId=upload_id,
                    Body=chunk,
                )
                parts.append({"PartNumber": part_number, "ETag": response["ETag"]})
                part_number += 1

            # 完成分块上传
            self.s3_client.complete_multipart_upload(
                Bucket=self.bucket_name,
                Key=remote_path,
                UploadId=upload_id,
                MultipartUpload={"Parts": parts},
            )

            logger.info(
                f"大文件对象分块上传成功: {self.bucket_name}/{remote_path}"
            )
            return True

        except Exception as e:
            logger.error(f"大文件对象分块上传失败 {remote_path}: {str(e)}")
            # 如果出错，中止分块上传
            if upload_id:
                try:
                    self.s3_client.abort_multipart_upload(
                        Bucket=self.bucket_name, Key=remote_path, UploadId=upload_id
                    )
                except:
                    pass
            return False


if __name__ == "__main__":
    oss_client = OSS()
    json_data = {"key": "value"}

    # 将字典转换为JSON字符串，然后转换为BytesIO对象
    json_string = json.dumps(json_data)
    json_bytes = json_string.encode("utf-8")
    json_byteio = io.BytesIO(json_bytes)
    oss_client.upload_doc_to_s3_and_get_path(json_byteio, "p1", "r1", "test.json")
