#!/usr/bin/python
# -*- coding:utf-8 -*-
import tty
import select
import os
from prettytable import PrettyTable
import datetime

import socket
import sys
from paramiko.py3compat import u
import django.utils.timezone

reload(sys)
sys.setdefaultencoding('utf-8')


class JumpServer(object):
    def __init__(self):
        self.basedir = (os.path.sep).join(os.path.abspath(__file__).split(os.path.sep)[:-2])
        sys.path.append(self.basedir)
        os.environ['DJANGO_SETTINGS_MODULE'] ='xebest.settings'
        import django
        django.setup()
        from cmdb import models
        self.models = models
        self.username = os.environ.get('SUDO_USER')
        current_time = datetime.datetime.now().strftime("%Y-%m-%d")
        file_name = 'logs/login_audit_%s_%s.log' % (self.username,current_time)
        self.fd = open(os.path.join(self.basedir,file_name),'a')

    def display_group(self,):
        group_query_set = self.user.server_group.all()
        self.group_dic = {}
        x = PrettyTable(["Id","GroupName","Count"])
        for i,g in enumerate(group_query_set):
            self.group_dic[i] = [g.id,g.group_name]
            x.add_row([i,g.group_name,g.servers.count()])
        print x

    def display_server(self,group_id,search=False,search_value=None):
        #server_query_set = self.models.Server.objects.filter(server_group_id = group_id)
        if search:
            server_query_set = self.models.ServerGroup.objects.get(id=group_id).servers.filter(server_name__icontains = search_value)
        else:
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
              #  logging.info(str(e))
            finally:
                sys.exit(1)
        else:
            self.user = self.models.OsUser.objects.get(username = self.username)


    def run(self):
        self.auth()
        while True:
            self.display_group()
            try:
                group_index = raw_input("\r\n\033[32;1mPlease input the group index or exit to quit the jumpserver: \033[0m\r\n")
            except KeyboardInterrupt:
                break
            except Exception,e:
                break
            if group_index.isdigit() and int(group_index) in self.group_dic.keys():
                search_tag = False
                search_value=''
                while True:

                    if search_tag:
                        self.display_server(self.group_dic[int(group_index)][0],search=True,search_value=search_value)
                        search_tag=False
                    else:
                        self.display_server(self.group_dic[int(group_index)][0])
                    try:
                        server_index = raw_input("\r\n\033[32;1mPlease input the server index or  exit to return to the group list or / for search server name ! \n\033[0m\r\n")
                    except KeyboardInterrupt:
                        break
                    except Exception,e:
                        break
                    if server_index.isdigit() and int(server_index) in self.server_dic.keys():
                        s = self.server_dic[int(server_index)]
                        self.login(s)
                    elif server_index.strip() == 'exit':
                        break
                    elif server_index.strip().startswith('/'):
                        search_tag = True
                    else:
                        print "\r\n\033[31;1mPlase input the right server index  or input exit return to group list !\033[0m\r\n"
                    search_value =  server_index.strip().replace('/','',1)
            elif group_index == 'exit':
                sys.exit()
            else:
                print '\r\n\033[31;1mPlease input the right group id or input exit to exit the jumpserver !\033[0m\r\n'
        self.fd.close()

    def deal_audit_log(self,cmd,s):
        current_time = django.utils.timezone.now()
        msg = '%s server name : %s , ip : %s , user : %s , cmd : %s ' % (current_time,s.server_name,s.ipaddr,self.username,cmd)
        self.fd.write(msg+os.linesep)
        self.fd.flush()

    def login(self,s):
        try:
            self.unsupport_cmd_list = ['rz','sz']
            tran = paramiko.Transport((s.ipaddr, s.port,))
            tran.connect(username=s.username, password=s.password)
            # 打开一个通道
            chan = tran.open_session()
            # 获取一个终端
            chan.get_pty()
            # 激活器
            chan.invoke_shell()
        except Exception,e:
            print '\r\n\033[31;1mLogin fail Please contact the server admin !!\033[0m\r\n'
           #  (str(e))
            return
        try:
            import termios
            import tty
            import time
            self.has_termios = True
        except ImportError:
            self.has_termios = False
        if self.has_termios:
            #print '--->posix:', main_ins.login_user,host_ip,username
            self.posix_shell(chan,s) #unix shell
        else:
            self.windows_shell(chan)


        chan.close()
        tran.close()



    def posix_shell(self,chan,s):
        import select

        oldtty = termios.tcgetattr(sys.stdin)
        try:
            tty.setraw(sys.stdin.fileno())
            tty.setcbreak(sys.stdin.fileno())
            chan.settimeout(0.0)


            cmd = ''
            tab_input_flag = False
            while True:
                r, w, e = select.select([chan, sys.stdin], [], [])

                if chan in r:
                    try:

                        x = u(chan.recv(1024))
                        if tab_input_flag:
                            cmd +=''.join(x[:10])
                            tab_input_flag = False
                        if len(x) == 0:
                            sys.stdout.write('\r\n\033[32;1m*** Session Closed ***\033[0m\r\n')
                            self.deal_audit_log('*** Session Closed ***',s)
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
                        if cmd in self.unsupport_cmd_list:
                            x="...Operation is not supported!\r\n"
                        cmd=''

                    if x == '\t':
                        tab_input_flag = True
                    chan.send(x)

            #f.close()
            #print cmd_list
        finally:
            termios.tcsetattr(sys.stdin, termios.TCSADRAIN, oldtty)


    # thanks to Mike Looijmans for this code
    def windows_shell(self,chan):
        import threading

        sys.stdout.write("Line-buffered terminal emulation. Press F6 or ^Z to send EOF.\r\n\r\n")

        def writeall(sock):
            while True:
                data = sock.recv(256)
                if not data:
                    sys.stdout.write('\r\n\033[32;1m*** Session closed ***\033[0m\r\n\r\n')
                    sys.stdout.flush()
                    break
                sys.stdout.write(data)
                sys.stdout.flush()

        writer = threading.Thread(target=writeall, args=(chan,))
        writer.start()

        try:
            while True:
                d = sys.stdin.read(1)
                if not d:
                    break
                chan.send(d)
        except EOFError:
            # user hit ^Z or F6
            pass

if __name__ == '__main__':
    j = JumpServer()
    j.run()

