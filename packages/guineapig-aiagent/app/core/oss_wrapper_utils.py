import os
import tempfile

from botocore.exceptions import ClientError

from .log import logger
from .oss import OSS

# 全局OSS客户端实例
_oss_client = None

def get_oss_client():
    """
    获取全局OSS客户端实例，单例模式
    """
    global _oss_client
    if _oss_client is None:
        _oss_client = OSS()
        logger.info("OSS客户端初始化完成")
    return _oss_client

def cleanup_oss_client():
    """
    清理全局OSS客户端实例，释放资源
    """
    global _oss_client
    if _oss_client is not None:
        # boto3客户端没有显式的close方法，但我们可以通过设置为None来释放引用
        _oss_client = None
        logger.info("OSS客户端已清理")

def upload_doc_to_s3_and_get_path(
    file_obj_or_path, project_id, file_path, filename=None
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
    try:
        oss_client = get_oss_client()

        # 确定远程文件名
        if isinstance(file_obj_or_path, str):
            # 如果是文件路径，使用原文件名
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

        # 上传文件
        oss_client._upload_single(file_obj_or_path, remote_path)

        logger.info(f"文件上传成功，远程路径: {remote_path}")
        return remote_path
    except Exception as e:
        logger.error(f"上传文件到OSS失败: {e}")
        raise


def upload_doc_to_s3(file_obj_or_path, project_id, file_path, filename=None):
    """上传文件到OSS并生成访问URL
    Args:
        file_obj_or_path: 文件路径（字符串）或文件对象（如BytesIO）
        project_id: 项目ID
        file_path: 文件路径
        filename: 可选，当传入文件对象时，用于指定文件名
    Returns:
        str: 访问URL
    """
    try:
        oss_client = get_oss_client()
        final_path = f"{project_id}/{file_path}"
        # 检查文件夹是否存在，如果不存在则创建
        if not oss_client.folder_exists(final_path):
            if not oss_client.create_folder(final_path):
                raise Exception(f"创建{final_path}文件夹失败")
        # 确定远程文件名
        if isinstance(file_obj_or_path, str):
            # 如果是文件路径，使用原文件名
            remote_filename = os.path.basename(file_obj_or_path)
        else:
            # 如果是文件对象，使用提供的文件名或默认名
            if filename:
                remote_filename = filename
            else:
                remote_filename = "uploaded_file.docx"
        # 上传文件
        remote_path = f"{final_path}/{remote_filename}"
        oss_client._upload_single(file_obj_or_path, remote_path)

        # 生成访问链接
        oss_link = oss_client.get_object_url(remote_path)
        logger.info(f"文件上传成功，访问链接: {oss_link}")
        return oss_link
    except Exception as e:
        logger.error(f"上传文件到OSS失败: {e}")
        raise


def upload_json_to_s3(req_id, json_str, file_path, json_filename):
    """上传JSON字符串到OSS并生成访问URL"""
    # 创建创建临时文件存储JSON内容
    with tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", delete=False, suffix=".json"
    ) as temp_file:
        # 写入JSON字符串到临时文件
        temp_file.write(json_str)
        local_path = temp_file.name  # 获取临时文件路径
    try:
        oss_client = get_oss_client()
        # 定义存储路径
        remote_path = f"{file_path}/{json_filename}"
        # 检查并创建文件夹
        if not oss_client.folder_exists(file_path):
            if not oss_client.create_folder(file_path):
                raise Exception(f"创建{file_path}文件夹失败")

        oss_client._upload_single(local_path, remote_path)

        # 生成访问链接
        oss_link = oss_client.get_object_url(remote_path)
        logger.info(
            f"req_id: {req_id}, 文件上传成功，访问链接: {oss_link}，文件地址：{remote_path}"
        )
        return remote_path
    except Exception as e:
        logger.warning(f"req_id: {req_id}, 上传文件到OSS失败: {e}")
        raise
    finally:
        # 确保临时文件被删除，避免残留
        if os.path.exists(local_path):
            try:
                os.remove(local_path)
                logger.debug(f"临时文件{local_path}已删除")
            except Exception as e:
                logger.warning(f"删除临时文件{local_path}失败: {e}")

def delete_file(project_id):
    """删除指定项目ID的文件夹及其内容"""
    try:
        oss_client = get_oss_client()
        if oss_client.folder_exists(project_id):
            return oss_client.delete_folder(project_id)
        else:
            logger.info(f"OSS文件夹 '{project_id}' 不存在，无需删除")
            return True
    except Exception as e:
        logger.error(f"删除OSS文件失败: {e}")
        return False


def download_file_from_s3(remote_path: str, local_path: str):
    """
    从 OSS/S3 下载单个文件到本地指定路径。
    Args:
        remote_path (str): OSS 中的对象键（例如 'file.txt'）
        local_path (str): 本地保存路径（例如 '/tmp/file.txt'）
    Returns:
        bool: 下载是否成功
    """
    # 确保本地目录存在
    local_dir = os.path.dirname(local_path)
    if local_dir and not os.path.exists(local_dir):
        os.makedirs(local_dir, exist_ok=True)
    try:
        oss_client = get_oss_client()
        oss_client._download_single(remote_path=remote_path, disk_path=local_path)
        logger.info(f"成功下载 {remote_path} 到 {local_path}")
        return True
    except ClientError as e:
        error_code = e.response["Error"]["Code"]
        if error_code == "404":
            logger.error(f"远程文件不存在: {remote_path}")
        elif error_code == "403":
            logger.error(f"无权限访问文件: {remote_path}")
        else:
            logger.error(f"下载失败 ({error_code}): {e}")
        return False
    except (IOError, OSError) as e:
        logger.error(f"本地写入失败: {local_path}: {e}")
        return False

def list_folders(prefix=""):
    """列出指定前缀下的所有文件夹（递归获取）
    Args:
        prefix: 目录前缀，为空则从根目录开始
    Returns:
        list: 文件夹路径列表（包含完整路径）
    """
    try:
        oss_client = get_oss_client()
        return oss_client.list_folders_recursive(prefix)
    except Exception as e:
        logger.error(f"列出文件夹失败: {e}")
        raise


def list_objects(prefix, suffix=None):
    """列出指定前缀下的所有对象
    Args:
        prefix: 对象前缀，用于过滤对象
        suffix: 可选，对象后缀，用于进一步过滤对象
    Returns:
        list: 对象列表，每个对象包含Key和其他元数据
    """
    try:
        oss_client = get_oss_client()
        return oss_client.list_objects(prefix, suffix)
    except Exception as e:
        logger.error(f"列出对象失败: {e}")
        raise