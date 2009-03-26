from ..sci_var import PseudoNetCDFFile, PseudoNetCDFVariable
from numpy import fromstring, vectorize, ndarray, array
from numpy.ma import MaskedArray
from datetime import datetime, timedelta
import re
import yaml
from warnings import warn

def get_lodval(v):
    try:
        return eval(v)
    except:
        return v

loddelim = re.compile('(;\s)|,|\s')

class ffi1001(PseudoNetCDFFile):
    def __init__(self,path):
        self.dimensions = {}
        self.variables = {}
        f = file(path, 'r')
        missing = []
        units = []
        l = f.readline()
        if l.split()[-1] != '1001':
            raise TypeError, "File is the wrong format.  Expected 1001; got %s" % (l.split()[-1],)
        
        n, self.fmt = l.split()
        n_user_comments = 0
        self.n_header_lines = int(n)
        for li in range(self.n_header_lines-1):
            li += 2
            l = f.readline()
            if li == 7:
                l = l.replace(',', '').split()
                SDATE = " ".join(l[:3])
                WDATE = " ".join(l[3:])
                self.SDATE = datetime.strptime(SDATE, '%Y %m %d')
                self.WDATE = datetime.strptime(WDATE, '%Y %m %d')
            elif li == 9:
                units.append(l.replace('\n', ''))
            elif li == 11:
                scales = [eval(i) for i in l.split()]
                if set([float(s) for s in scales]) != set([1.]):
                    raise ValueError, "Unsupported: scaling is unsupported.  data is scaled by %s" % (str(scales),)
            elif li == 12:
                missing = [eval(i) for i in l.split()]
            elif li > 12 and li <= 12+len(missing):
                nameunit = l.replace('\n','').split(',')
                name = nameunit[0].strip()
                if len(nameunit) > 1:
                    units.append(nameunit[1])
                elif re.compile('(.*)\((.*)\)').match(nameunit[0]):
                    desc_groups = re.compile('(.*)\((.*)\).*').match(nameunit[0]).groups()
                    name = desc_groups[0].strip()
                    units.append(desc_groups[1].strip())
                elif '_' in name:
                    units.append(name.split('_')[1])
                else:
                    warn('Could not find unit in string: "%s"' % l)
                    units.append(name)
            elif li == 12+len(missing)+2:
                n_user_comments = int(l.replace('\n',''))
            elif li > 12+len(missing)+2 and li < self.n_header_lines:
                colon_pos = l.find(':')
                k = l[:colon_pos].strip()
                v = l[colon_pos+1:].strip()
                setattr(self,k,v)
            elif li == self.n_header_lines:
                variables = l.replace(',','').split()
                self.TFLAG = variables[0]

        missing = missing[:1]+missing
        scales = [1.]+scales
        
        if hasattr(self,'LLOD_FLAG'):
            llod_values = loddelim.sub('\n', self.LLOD_VALUE).split()
            if len(llod_values) == 1:
                llod_values *= len(variables)
            else:
                llod_values = ['N/A']+llod_values
            
            assert len(llod_values) == len(variables)
            llod_values = [get_lodval(llod_val) for llod_val in llod_values]
            
            llod_flags = len(llod_values)*[self.LLOD_FLAG]
            llod_flags = [get_lodval(llod_flag) for llod_flag in llod_flags]
        
        if hasattr(self,'ULOD_FLAG'):
            ulod_values = loddelim.sub('\n', self.ULOD_VALUE).split()
            if len(ulod_values) == 1:
                ulod_values *= len(variables)
            else:
                ulod_values = ['N/A']+ulod_values

            assert len(ulod_values) == len(variables)
            ulod_values = [get_lodval(ulod_val) for ulod_val in ulod_values]
            
            ulod_flags = len(ulod_values)*[self.ULOD_FLAG]
            ulod_flags = [get_lodval(ulod_flag) for ulod_flag in ulod_flags]
        
        data = f.read()
        datalines = data.split('\n')
        ndatalines = len(datalines)
        while datalines[-1] in ('', ' ', '\r'):
            ndatalines -=1
            datalines.pop(-1)
        data = fromstring(data,dtype ='d', sep = ' ')
        data = data.reshape(ndatalines,len(variables))
        data = data.swapaxes(0,1)
        self.createDimension('POINTS', ndatalines)
        for var, scale, miss, unit, dat, llod_flag, llod_val, ulod_flag, ulod_val in zip(variables, scales, missing, units, data, llod_flags, llod_values, ulod_flags, ulod_values):
            vals = MaskedArray(dat, mask = dat == miss)
            tmpvar = self.variables[var] = PseudoNetCDFVariable(self, var, 'f', ('POINTS',), values = vals)
            tmpvar.units = unit

            tmpvar.fill_value = miss
            tmpvar.scale = scale

            if hasattr(self,'LLOD_FLAG'):
                tmpvar.llod_flag = llod_flag
                tmpvar.llod_value = llod_val

            if hasattr(self,'ULOD_FLAG'):
                tmpvar.ulod_flag = ulod_flag
                tmpvar.ulod_value = ulod_val

            tmpvar[:] = dat
        
        
        self.date_objs = self.SDATE + vectorize(lambda s: timedelta(seconds = int(s), microseconds = (s - int(s)) * 1.E6 ))(self.variables[self.TFLAG]).view(type = ndarray)
        self.createDimension('YYYYMMDDTHHMMSS.microS', 22)
        var = self.createVariable('TFLAG', 'c', ('POINTS', 'YYYYMMDDTHHMMSS.microS'))
        var[:] = array(['%(Y)04d%(m)02d%(d)02dT%(H)02d%(M)02d%(S)02d.%(f)06d' % dict(Y = d.year, m = d.month, d = d.day, H = d.hour, M = d.minute, S = d.second, f = d.microsecond) for d in self.date_objs], dtype = '|S22').view('|S1').reshape(self.date_objs.shape[0], self.dimensions['YYYYMMDDTHHMMSS.microS'])
        var.units = 'YYYYMMDDTHHMMSS.microS'
        var.fill_value = ''
        var.scale = 1.
