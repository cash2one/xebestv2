# -*- coding:utf-8 -*-
import sys
import paramiko
import termios
import tty
import socket
import select
import sys,os
from prettytable import PrettyTable
import datetime
from paramiko.py3compat import u
import logging

class JumpServer(object):
    def __init__(self):
        self.basedir = (os.path.sep).join(os.path.abspath(__file__).split(os.path.sep)[:-2])
        sys.path.append(self.basedir)
        os.environ['DJANGO_SETTINGS_MODULE'] ='xebest.settings'
        import django
        django.setup()
        from cmdb import models
        self.models = models
        self.username = os.environ.get('LOGNAME')
        current_time = datetime.datetime.now().strftime("%Y-%m-%d")
        file_name = 'logs/login_audit_%s_%s.log' % (self.username,current_time)
        self.fd = open(os.path.join(self.basedir,file_name),'a')

    def display_group(self,):
        group_query_set = self.user.server_group.all()
        self.group_dic = {}
        x = PrettyTable(["Id","GroupName"])
        for i,g in enumerate(group_query_set):
            self.group_dic[i] = [g.id,g.group_name]
            x.add_row([i,g.group_name])
        print x

    def display_server(self,group_id):
        #server_query_set = self.models.Server.objects.filter(server_group_id = group_id)
        server_query_set = self.models.ServerGroup.objects.get(id=group_id).servers.all()
        self.server_dic = {}
        x = PrettyTable(["Id","ServerName","IpAddress" ,"Port"])
        for i,s in enumerate(server_query_set):
            self.server_dic[i] = s
            x.add_row([i,s.server_name,s.ipaddr,s.port])
        print x


    def auth(self):
        username_list = self.models.OsUser.objects.values_list('username',flat=True)
        if self.username not in username_list:
            try:

                raw_input( '''You don't have permission to login to this jumpserver ''')
                sys.exit(1)
            except Exception , e:
                sys.exit(1)
                logging.info(str(e))
            finally:
                sys.exit(1)
        else:
            self.user = self.models.OsUser.objects.get(username = self.username)


    def run(self):
        self.auth()
        while True:
            self.display_group()
            try:
                group_index = raw_input("Please input the group index : ")
            except KeyboardInterrupt:
                break
            if group_index.isdigit() and int(group_index) in self.group_dic.keys():
                while True:
                    self.display_server(self.group_dic[int(group_index)][0])
                    try:
                        server_index = raw_input("Please input the server index : ")
                    except KeyboardInterrupt:
                        break
                    if server_index.isdigit() and int(server_index) in self.server_dic.keys():
                        s = self.server_dic[int(server_index)]
                        self.login(s)
                    else:
                        print "Plase input the right server index !"

            else:
                print 'Please input the right group id '
        self.fd.close()

    def deal_audit_log(self,cmd,s):
        current_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        msg = 'server name : %s , ip : %s , user : %s , cmd : %s ' % (s.server_name,s.ipaddr,self.username,cmd)
        self.fd.write(msg+os.linesep)
        self.fd.flush()

    def login(self,s):
        try:
            unsupport_cmd_list = ['rz','sz']
            tran = paramiko.Transport((s.ipaddr, s.port,))
            tran.connect(username=s.username, password=s.password)
            # 打开一个通道
            chan = tran.open_session()
            # 获取一个终端
            chan.get_pty()
            # 激活器
            chan.invoke_shell()
            oldtty = termios.tcgetattr(sys.stdin)
        except Exception,e:
            print '\r\n\033[31;1mLogin fail Please connect the server admin !!\033[0m\r\n'
            logging.info(str(e))
            return

        try:
            # 为tty设置新属性
            # 默认当前tty设备属性：
            #   输入一行回车，执行
            #   CTRL+C 进程退出，遇到特殊字符，特殊处理。

            # 这是为原始模式，不认识所有特殊符号
            # 放置特殊字符应用在当前终端，如此设置，将所有的用户输入均发送到远程服务器
            tty.setraw(sys.stdin.fileno())
            tty.setcbreak(sys.stdin.fileno())
            chan.settimeout(0.0)
            cmd = ''
            tab_input_flag = False
            while True:
                # 监视 用户输入 和 远程服务器返回数据（socket）
                # 阻塞，直到句柄可读
                r, w, e = select.select([chan, sys.stdin], [], [], 1)
                if chan in r:
                    try:
                        x = u(chan.recv(1024))
                        if tab_input_flag:
                            cmd +=''.join(x[:10])
                            tab_input_flag = False
                        if len(x) == 0:
                            sys.stdout.write('\r\n\033[32;1m*** Session Closed ***\033[0m\r\n')
                            self.deal_audit_log("*** Session Closed ***",s)
                            break

                        sys.stdout.write(x)
                        sys.stdout.flush()

                    except socket.timeout:
                        pass
                    except UnicodeDecodeError,e:
                        pass
                if sys.stdin in r:
                    x = sys.stdin.read(1)
                    if len(x) == 0:
                        break
                    if not x == '\r':
                        cmd +=x
                    else:
                        if len(cmd.strip())>0:
                            self.deal_audit_log(cmd,s)
                        if cmd in unsupport_cmd_list:
                            x="...Operation is not supported!\r\n"
                        cmd=''

                    if x == '\t':
                        tab_input_flag = True
                    chan.send(x)

        finally:
            # 重新设置终端属性
            termios.tcsetattr(sys.stdin, termios.TCSADRAIN, oldtty)


        chan.close()
        tran.close()



if __name__ == '__main__':
    j = JumpServer()
    j.run()

