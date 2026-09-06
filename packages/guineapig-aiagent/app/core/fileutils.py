import os
import shutil

from app.core.log import logger


class FileUtils:
    """文件操作工具类，提供常用的文件和目录处理方法"""

    @staticmethod
    def get_context_path() -> str:
        """获取项目根目录"""
        import sys

        return os.path.abspath(sys.path[0])

    @staticmethod
    def read_file(path: str) -> str:
        """读取文件内容（UTF-8编码）"""
        try:
            with open(path, "r", encoding="utf-8") as f:
                return f.read()
        except Exception as e:
            logger.error(f"读取文件错误: {e}")
            return ""

    @staticmethod
    def get_files_name(folder_path: str, query_str: str = None) -> dict:
        """
        获取文件夹下所有文件和文件夹名称，支持模糊查询
        返回字典包含:
        - retType: 1(路径不存在)、2(是文件)、3(是文件夹)
        - 其他相关信息
        """
        result = {}
        query_str = query_str or ""
        f = os.path.abspath(folder_path)

        if not os.path.exists(f):
            result["retType"] = "1"
        elif os.path.isfile(f):
            result["retType"] = "2"
            result["fileName"] = os.path.basename(f)
        else:
            result["retType"] = "3"
            file_names = []
            folder_names = []

            for item in os.listdir(f):
                if query_str in item:
                    item_path = os.path.join(f, item)
                    if os.path.isdir(item_path):
                        folder_names.append(item)
                    else:
                        file_names.append(item)

            result["fileNameList"] = file_names
            result["folderNameList"] = folder_names

        return result

    @staticmethod
    def read_file_content(file_path: str) -> list:
        """按行读取文件内容，返回行列表"""
        content = []
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                for line in f:
                    content.append(line.rstrip("\n"))
        except Exception as e:
            logger.error(f"读取文件内容错误: {e}")
        return content

    @staticmethod
    def read_line_content(file_path: str, line_number: int) -> str:
        """读取指定行内容（0为起始行）"""
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                for i, line in enumerate(f):
                    if i == line_number:
                        return line.rstrip("\n")
            return ""
        except Exception as e:
            logger.error(f"读取指定行错误: {e}")
            return ""

    @staticmethod
    def read_lines_content(file_path: str, begin_line: int, end_line: int) -> list:
        """读取从begin_line到end_line的内容（包含首尾，0为起始行）"""
        content = []
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                for i, line in enumerate(f):
                    if begin_line <= i <= end_line:
                        content.append(line.rstrip("\n"))
        except Exception as e:
            logger.error(f"读取行范围错误: {e}")
        return content

    @staticmethod
    def read_file_content_list(file_paths: list) -> list:
        """读取多个文件的所有内容"""
        content = []
        for path in file_paths:
            content.extend(FileUtils.read_file_content(path))
        return content

    @staticmethod
    def file_lines_write(file_path: str, content: str, append: bool = True) -> str:
        """
        写入文件内容
        :param file_path: 文件路径
        :param content: 要写入的内容
        :param append: 是否追加模式
        :return: 操作结果（create/write）
        """
        try:
            # 创建父目录
            parent_dir = os.path.dirname(file_path)
            if not os.path.exists(parent_dir):
                os.makedirs(parent_dir, exist_ok=True)

            # 判断文件是否存在
            is_new = not os.path.exists(file_path)

            # 写入内容
            mode = "a" if append else "w"
            with open(file_path, mode, encoding="utf-8") as f:
                f.write(content + "\n")

            return "create" if is_new else "write"
        except Exception as e:
            logger.error(f"写入文件错误: {e}")
            return ""

    @staticmethod
    def delete_everything(file_path: str) -> None:
        """递归删除文件或目录"""
        if not os.path.exists(file_path):
            return

        if os.path.isfile(file_path):
            os.remove(file_path)
        else:
            for item in os.listdir(file_path):
                item_path = os.path.join(file_path, item)
                FileUtils.delete_everything(item_path)
            os.rmdir(file_path)

    @staticmethod
    def mk_dir(dir_path: str) -> None:
        """创建目录"""
        try:
            if not os.path.exists(dir_path):
                os.makedirs(dir_path, exist_ok=True)
        except Exception as e:
            logger.error(f"创建目录错误: {e}")

    @staticmethod
    def is_file_exist(file_name: str) -> bool:
        """判断文件是否存在"""
        return os.path.isfile(file_name)

    @staticmethod
    def get_file_ext(file_name: str) -> str:
        """获取文件后缀名"""
        _, ext = os.path.splitext(file_name)
        return ext[1:] if ext else ""

    @staticmethod
    def delete_dir(dir_path: str) -> None:
        """删除目录及其子目录"""
        if not os.path.isdir(dir_path):
            raise NotADirectoryError(f"{dir_path} 不是一个目录")
        shutil.rmtree(dir_path, ignore_errors=True)

    @staticmethod
    def copy(src: str, dst: str) -> None:
        """复制文件"""
        try:
            shutil.copy2(src, dst)
        except Exception as e:
            logger.error(f"复制文件错误: {e}")
            raise


if __name__ == "__main__":
    print(FileUtils.get_context_path())
    # print(FileUtils.copy("./test.txt", "./test_copy.txt"))
    # print(FileUtils.read_file_content_list(["./test.txt"]))
    # print(FileUtils.read_file_content("./test.txt"))
    # print(FileUtils.read_file("./test.txt"))
    # print(
    #     FileUtils.string_to_array(
    #         "a,b,c,d,e,f,g,h,i,j,k,l,m,n,o,p,q,r,s,t,u,v,w,x,y,z", ","
    #     )
    # )
