import sys
import os
import time
import commands
import threading
import subprocess
import tempfile
import signal
import time
import pickle
from xml.dom.minidom import parseString
import xml.dom.ext as ext

try:
    from hackzor.evaluator.settings import *
    from hackzor.settings import MEDIA_ROOT
    #from server.models import Attempt, ToBeEvaluated, BeingEvaluated
except ImportError:
    C_COMPILE_STR = 'gcc -lm -w \'%i\' -o \'%o\''
    CPP_COMPILE_STR = 'g++ -lm -w \%i\' -o \'%o\''
    JAVA_COMPILE_STR = 'javac \'%i\' -d \'%o\''
    WORK_DIR = 'evaluator/work_files'


class EvaluatorError(Exception):
    def __init__(self, error, value=''):
        self.value = value
        self.error = error

    def __str__(self):
        return 'Error: '+self.error+'\tValue: '+ self.value


class XMLParser:
    """This base class will contain all the functions needed for the XML file
    to be parsed
    NOTE: This class is not to be instantiated
    """
    def __init__(self):
        raise NotImplementedError('XMLParser class is not to be instantiated')
    
    def get_val_by_id(self, root, id):
        """This function will get the value of the `id' child node of
        `root' node. `root' should be of type DOM Element. e.g.
        root
        |
        |-- <id>value-to-be-returned</id>"""
        
        child_node = root.getElementsByTagName(id)
        if not child_node:
            raise EvaluatorError('Invalid XML file')
        return child_node[0].nodeValue

    def add_node(doc, root, child, value):
        """ Used to add a text node 'child' with the value of 'value'(duh..) """
        node = doc.createElement(child)
        node.appendChild(doc.createTextNode(value))
        root.appendChild(node)

    
class Question(XMLParser):
    """Defines the Characteristics of each question in the contest"""
    def __init__(self, qn):
        self.input_data = self.get_val_by_id(qn, 'input-data')
        # TODO: Consider grouping all the contraint variables inside a `Limit'
        # class
        self.time_limit = float(self.get_val_by_id(qn, 'time-limit'))
        self.mem_limit = int(self.get_val_by_id(qn, 'mem-limit'))
        self.save_eval_to_disk(qn)

    def save_eval_to_disk(self, qn):
        """This function will unpickle the evaluator, sent from web server and
        save it into a file in the directory `evaluators' in the name of the
        question id"""
        # Save the pickled Evaluator binary to disk
        evaluator = qn.getElementsByName('evaluator')[0].firstChild.nodeValue
        self.eval_file_path = os.path.join('evaluators', qn.getAttribute('id'))
        eval_file = open(self.eval_file_path, 'w')
        eval_file.write(evaluator)
        eval_file.close()
        eval_file = open(self.eval_file_path, 'r')
        del evaluator
        evaluator = pickle.load(eval_file)
        eval_file.close()
        eval_file = open(self.eval_file_path, 'w')
        eval_file.write(evaluator)
        eval_file.close()
        os.chmod(self.eval_file_path, 0700) # set executable permission for
                                        # evaluator
    
class Questions(XMLParser):
    """Set of all questions in the contest"""
    def __init__(self, xml_file):
        xml = parseString(xml_file)
        qn_set = xml.getElementsByTagName('question-set')
        if not qn_set:
            #return error here
            pass
        self.questions = {}
        for qn in qn_set:
            questions[qn.getAttribute('id')] = Question(qn)
                        

class Attempt(XMLParser):
    """Each Attempt XML file is parsed by this class"""
    def __init__(self, xml_file):
        xml = parseString(xml_file)
        attempt = xml.getElementsByTagName('attempt')
        if not attempt:
            #return error here
            pass
        attempt = attempt[0]
        self.aid = get_val_by_id(attempt, 'aid')
        self.qid = get_val_by_id(attempt, 'qid')
        self.code = get_val_by_id(attempt, 'code')
        self.lang = get_val_by_id(attempt, 'lang')
        self.file_name = get_val_by_id(attempt, 'file-name')
        
    def get_val_by_id(self, attempt, id):
        child_node = attempt.getElementsByTagName(id)
        if not child_node:
            raise EvaluatorError('Invalid XML file')
        return child_node[0].nodeValue

    def convert_to_result(self, result):
        """Converts an attempt into a corresponding XML file to notify result"""
        doc = minidom.Document()
        root = doc.createElementNS('http://code.google.com/p/hackzor', 'attempt')
        doc.appendChild(root)
        add_node(doc, root, 'aid', self.aid)
        add_node(doc, root, 'result', str(result))
        return ext.Print(doc)
        
## TODO: Write about the parameter to methods in each of their doc strings
class Evaluator:
    """Provides the base functions for evaluating an attempt.
    NOTE: This class is not to be instantiated"""
    def __str__(self):
        raise NotImplementedError('Must be Overridden')

    def compile(self, code_file, input_file):
        raise NotImplementedError('Must be Overridden')

    def get_run_cmd(self, exec_file):
        raise NotImplementedError('Must be Overridden')

    def run(self, cmd, input_file):
        output_file = tempfile.NamedTemporaryFile()
        input_file = os.path.join(MEDIA_ROOT,input_file)
        print 'Input File: ',input_file
        print 'Output File: ',output_file.name
        # cmd = cmd + ' < ' + input_file + ' > ' + output_file.name
        inp_file = open(input_file,'r')
        kws = {'shell':True, 'stdin':inp_file, 'stdout':output_file.file}
        start_time = time.time()
        p = subprocess.Popen(cmd, **kws)
        while True:
            if time.time() - start_time >= 5:
                # TODO: Verify this!!! IMPORTANT
                os.kill(p.pid, signal.SIGTERM)
                #os.system('pkill -P '+str(p.pid)) # Try to implement pkill -P internally
                print 'Killed Process Tree: '+str(p.pid)
                raise EvaluatorError('Time Limit Expired')
            elif p.poll() != None:
                break
            time.sleep(0.5)
        if p.returncode != 0:
            raise EvaluatorError('Run-Time Error')
        else:
            output_file.file.flush()
            output_file.file.seek(0)
            output = output_file.file.read()
            output_file.close()
        return output

    def save_file(self, file_path, contents):
        """ Save the contents in the file given by file_path relative inside
        the WORK_DIR directory"""
        if not os.path.exists(WORK_DIR):
            os.mkdir(WORK_DIR)
        file_path = os.path.join(WORK_DIR, file_path)
        open_file = open(file_path, 'w')
        open_file.write(contents)
        open_file.close()
        return file_path

    def evaluate(self, attempt):
        # Save the File
        save_loc = attempt.aid + '-' + attempt.qid + '-' + attempt.file_name
        code_file = self.save_file(save_loc, attempt.code)
        # Java has this dirty requirement that the file name be the same as the
        # main class name. So having a workaround. The attempts are saved
        #(for archival purposes only) and java files are also saved in a
        # temporary directory called java
        if attempt.lang == 'java':
            save_loc = os.path.join('java', attempt.file_name)
            code_file = self.save_file(save_loc, attempt.code)

        # Compile the File
        exec_file = self.compile(code_file)

        cmd = self.get_run_cmd(exec_file)
        
        # Execute the file for preset input
        output = self.run(cmd, attempt.question.test_input)

        # Match the output to expected output
        return self.check(attempt, output)

    def check(self, attempt, output):
        eval_path = os.path.join(MEDIA_ROOT, attempt.question.evaluator_path)
        if eval_path[-3:] != '.py':
            raise EvaluatorError('Evalutor Not Supported')
        eval_path = eval_path[:-3]
        compare = __import__(eval_path)
        result =  compare.compare(output)
        return result


class C_Evaluator(Evaluator):
    def __init__(self):
        self.compile_cmd = C_COMPILE_STR
        
    def __str__(self):
        return 'C Evaluator'

    def get_run_cmd(self, exec_file):
        return exec_file

    def compile(self, code_file):
        output_file = code_file # Change this value to change output file name
        # replace the code with the object file
        cmd = self.compile_cmd.replace('%i',code_file).replace('%o',output_file)

       (status, output) = commands.getstatusoutput(cmd)
        if status != 0:
            raise EvaluatorError('Compiler Error', output)
        else:
            return output_file


class CPP_Evaluator(C_Evaluator):
    def __init__(self):
        self.compile_cmd = CPP_COMPILE_STR

    def __str__(self):
        return 'C++ Evaluator'
    

class Java_Evaluator(Evaluator):
    def __str__(self):
        return 'Java Evaluator'

    def __init__(self):
        self.compile_cmd = JAVA_COMPILE_STR

    def get_run_cmd(self, exec_file):
        return 'java '+exec_file

    def compile(self, code_file):
        output_dir, file_name = os.path.split(code_file)
        cmd = self.compile_cmd.replace('%i',code_file).replace('%o',
                                                                output_dir)
        if file_name [-5:] != '.java':
            raise EvaluatorError('Compiler Error', 'Not a Java File')
        file_name = file_name [:-5]
       (status, output) = commands.getstatusoutput(cmd)
        if status != 0:
            raise EvaluatorError('Compiler Error', output)
        else:
            return file_name


class Python_Evaluator(Evaluator):
    def __str__(self):
        return 'Python Evaluator'

    def compile(self, code_file):
        """ Nothing to Compile in the case of Python. Aha *Magic*!"""
        return code_file

    def get_run_cmd(self, exec_file):
        return 'python '+exec_file
    

class Client:
    """ The Evaluator will evaluate and update the status """
    # TODO: Avoid HardCoding Language Options
    evaluators = {'c':C_Evaluator, 'c++':CPP_Evaluator,
                  'java':Java_Evaluator, 'python':Python_Evaluator}
    
    def __init__(self):
        key_id = '' # TODO: get key-id from GPG keyring
        root_url = CONTEST_URL + '/evaluator/'+key_id
        self.get_attempt_url = root_url + '/getattempt'
        self.submit_attempt_url_select = '/evaluator/'+key_id + '/submitattempt'
        self.get_qns = root_url + '/getquestions'
        cj = cookielib.CookieJar()
        self.cookie_opener = urllib2.build_opener(urllib2.HTTPCookieProcessor(cj))
        urllib2.install_opener(cookie_opener)

        # Initialise the question Table
        req = urllib2.Request(self.get_qns, None)
        self.question_set = Questions(req.read())
    
    def get_attempt(self):
        """ Keep polling the server until an attempt to be evaluated is
        obtained """
        req = urllib2.Request(self.get_attempt_url, None)
        req = urllib2.urlopen(req)
        return Attempt(req.read())

    def score(self, result, score):
        """Apply a function on the result to generate the score.. in case you
        want to have step wise scoring"""
        ## TODO: The scoring logic should be moved into the question setter's
        ## evaluator logic
        if result == True:
            return score
        else:
            return 0

    def evaluate(self, attempt):
        """ Evaluate the attempt and return the ruling :-) 
            attempt : An instance of the Attempt Class
            return value : Boolean, the result of the evaluation.
            """
        lang = attempt.lang.lower()
        # first list special case languages whose names cannot be used for
        # function names in python
        try:
            evaluator = self.evaluators[lang]()
            return evaluator.evaluate(attempt)
        except KeyError:
            raise NotImplementedError('Language '+lang+' not supported')

    def submit_attempt(self, attempt_xml):
        host = CONTEST_URL
        selector = self.submit_attempt_url_select
        headers = {'Content-Type': 'application/xml',
                   'Content-Length': str(len(attempt_xml))}
        r = urllib2.Request("http://%s%s" %(host, selector), body, headers)
        return urllib2.urlopen(r).read()        
        
    def start(self):
        print 'Evaluator Started'
        while True:
            attempt = self.get_attempt()
            if attempt == None:
                # No attempts in web server queue to evaluate
                time.sleep(TIME_INTERVAL)
                continue
            # evalute the attempt
            try:
                return_value = self.evaluate(attempt)
            except EvaluatorError:
                print 'EvaluatorError: '
                print sys.exc_info()[1].error
                return_value = False
            print 'Final Result: ', return_value
            self.submit_attempt(attempt.convert_to_result(return_value))
            # TODO: Convert this into a suitable result XML file and respond
        return return_value


if __name__ == '__main__':
    Client().start()