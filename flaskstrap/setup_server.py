from .utils import dprint
from .utils import get_project_name
from .utils import get_current_path
from getpass import getpass
import sys
import os
import paramiko

client = paramiko.SSHClient()
client.load_system_host_keys()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

# Support Python 2 and 3 input
# Default to Python 3's input()
get_input = input

# If this is Python 2, use raw_input()
if sys.version_info[:2] <= (2, 7):
	get_input = raw_input


def create_user():
	global username
	username = get_input('name of user to create: ')

	cmd1 = 'adduser %s --gecos "First Last,RoomNumber,WorkPhone,HomePhone" --disabled-password' % username
	ssh_stdin, ssh_stdout, ssh_stderr = client.exec_command(cmd1)
	output = ssh_stdout.read().decode('ascii')
	print(output)

	password = getpass('enter password for new user: ')
	ssh_stdin, ssh_stdout, ssh_stderr = client.exec_command('echo "%s:%s" | sudo chpasswd' % (username, password))
	output = ssh_stdout.read().decode('ascii')
	print(output)

	ssh_stdin, ssh_stdout, ssh_stderr = client.exec_command('usermod -aG sudo %s' % username)
	output = ssh_stdout.read().decode('ascii')
	print(output)

	answer = get_input('do you want to copy your public key to the server for trusted ssh login? (y/n): ')
	if answer == 'yes' or answer == 'y' or answer == 'Y':
		add_public_key(username)

	answer = get_input('enable ssh password authentication? (y/n): ')
	if answer == 'yes' or answer == 'y' or answer == 'Y':
		enable_password_auth()


def enable_password_auth():
	sftp_client = client.open_sftp()

	with sftp_client.open('/etc/ssh/sshd_config', 'r+') as f:
		lines = f.readlines()
		f.seek(0)
		f.truncate(0)
		for line in lines:
			if 'PasswordAuthentication no' in line:
				line = line.replace('PasswordAuthentication no', 'PasswordAuthentication yes')
			f.write(line)

	sftp_client.close()
	ssh_stdin, ssh_stdout, ssh_stderr = client.exec_command('service ssh reload')


def add_public_key(username):
	cmd1 = 'mkdir -p /home/{0}/.ssh'.format(username)
	ssh_stdin, ssh_stdout, ssh_stderr = client.exec_command(cmd1)

	cmd2 = 'touch /home/{0}/.ssh/authorized_keys'.format(username)
	ssh_stdin, ssh_stdout, ssh_stderr = client.exec_command(cmd2)

	#cmd3 = 'chown -R %s:%s /home/%s/.ssh' % username
	cmd3 = 'chown -R {0}:{0} /home/{0}/.ssh'.format(username)
	ssh_stdin, ssh_stdout, ssh_stderr = client.exec_command(cmd3)

	cmd4 = 'chmod 0700 /home/{0}/.ssh'.format(username)
	ssh_stdin, ssh_stdout, ssh_stderr = client.exec_command(cmd4)

	cmd5 = 'chmod 0600 /home/{0}/.ssh/authorized_keys'.format(username)
	ssh_stdin, ssh_stdout, ssh_stderr = client.exec_command(cmd5)

	home_dir = os.path.expanduser('~')
	public_key_dir = os.path.join(home_dir, '.ssh/id_rsa.pub')

	with open(public_key_dir, 'r') as pub_key_file:
		public_key = pub_key_file.read()

	sftp_client = client.open_sftp()
	authorized_keys = sftp_client.open('/home/{0}/.ssh/authorized_keys'.format(username), 'a')
	authorized_keys.write(public_key)
	authorized_keys.close()

	sftp_client.close()


def install_dependencies():
	update = 'apt-get update'
	ssh_stdin, ssh_stdout, ssh_stderr = client.exec_command(update)
	output = ssh_stdout.read().decode('ascii')
	print(output)

	install = 'apt-get -y install python-pip python-dev nginx python-virtualenv'
	print('installing nginx and pip')
	ssh_stdin, ssh_stdout, ssh_stderr = client.exec_command(install)
	output = ssh_stdout.read().decode('ascii')
	print(output)

	print('installing virtualenv')
	ssh_stdin, ssh_stdout, ssh_stderr = client.exec_command('pip install virtualenv')
	output = ssh_stdout.read().decode('ascii')
	print(output)
	print('finished')


def create_virtualenv():
	print('creating virtualenv')
	mk_virtualenv_dir = 'mkdir -p /home/{0}/.virtualenvs'.format(username)
	print(mk_virtualenv_dir)
	ssh_stdin, ssh_stdout, ssh_stderr = client.exec_command(mk_virtualenv_dir)
	output = ssh_stdout.read().decode('ascii')

	# for now get the project name from current working directory
	# later read this from project_settings.yml
	project_name = os.getcwd().split('/')[-1]
	mk_virtualenv = 'virtualenv /home/{0}/.virtualenvs/{1}'.format(username, project_name)
	print(mk_virtualenv)
	ssh_stdin, ssh_stdout, ssh_stderr = client.exec_command(mk_virtualenv)
	output = ssh_stdout.read().decode('ascii')
	print(output)

	# install virtualenv dependencies
	virtualenv_deps = '/home/{0}/.virtualenvs/{1}/bin/pip install uwsgi flask'.format(username, project_name)
	print(virtualenv_deps)
	ssh_stdin, ssh_stdout, ssh_stderr = client.exec_command(virtualenv_deps)
	output = ssh_stdout.read().decode('ascii')
	print(output)


def setup_nginx_site():
	project_name = get_project_name()
	curr_path = get_current_path()
	nginx_conf_path = os.path.join(curr_path, 'templates/nginx_conf')

	with open(nginx_conf_path, 'r') as nginx_conf_file:
		nginx_conf = nginx_conf_file.read()

	sftp_client = client.open_sftp()

	nginx_conf_file = sftp_client.open('/etc/nginx/sites-available/{0}'.format(project_name), 'w+')
	nginx_conf_file.write(nginx_conf)
	nginx_conf_file.close()

	sftp_client.close()

	cmd = 'ln -s /etc/nginx/sites-available/{0} /etc/nginx/sites-enabled'.format(project_name)
	ssh_stdin, ssh_stdout, ssh_stderr = client.exec_command(cmd)
	output = ssh_stdout.read().decode('ascii')
	print(output)

	ssh_stdin, ssh_stdout, ssh_stderr = client.exec_command('nginx -t')
	ssh_stdin, ssh_stdout, ssh_stderr = client.exec_command('service nginx restart')



def run(args):
	global host
	dprint('running server setup')
	cwd = os.getcwd()
	interpreter = sys.executable
	dprint('cwd: ' + cwd)
	dprint('interpreter: ' + interpreter)
	try:
		host = args.get('name', None)[0]
	except Exception:
		host = get_input('host address: ')
		#exit('host address missing')
	try:
		client.connect(host, username='root')
	except paramiko.ssh_exception.AuthenticationException:
		print('ssh connection failed to use public key')
		password = getpass('password for root: ')
		try:
			client.connect(host, username='root', password=password)
		except paramiko.ssh_exception.AuthenticationException:
			exit('connection failed')

	print('connection established')
	create_user()
	install_dependencies()
	create_virtualenv()
	setup_nginx_site()

	client.close()