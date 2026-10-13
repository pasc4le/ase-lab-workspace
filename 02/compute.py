BASE_CPI = 1

def make(alu, mul, div, std = BASE_CPI, stalls = 0):
    return {
        'alu': alu,
        'mul': mul,
        'div': div,
        'std': std,
        'stalls': stalls,
    }

def boildown(cpu, d):
    return (
        cpu['alu'] * d.get('alu', 0)
        + cpu['mul'] * d.get('mul', 0)
        + cpu['div'] * d.get('div', 0)
        + cpu['std'] * (d.get('alu', 0) + d.get('mul', 0) + d.get('div', 0) + d.get('std', 0))
        + d.get('stalls', 0)
    )

fixed = make(alu=5, mul=0, div=1, std=6 + 9 + 1 + 4, stalls=3)
loop = make(alu=1, mul=0, div=0, std=5, stalls=4)

def compute(cpu, k = 30):
    # fixed part
    cc = boildown(cpu, fixed)

    # loop
    ccl = k * boildown(cpu, loop)

    return cc + ccl

BASE_HZ = 15e6

def time(cc, hz = BASE_HZ):
    return cc / hz

if __name__ == "__main__":
    # 1.1
    configs = {
        "init": make(alu=4-1, mul=6-1, div=30-1),
        "b1": make(alu=4-1, mul=2-1, div=30-1),
        "b2": make(alu=4-1, mul=6-1, div=10-1),
    }
    
    for name, cpu in configs.items():
        print(cpu)
        cc = compute(cpu)
        print(name, cc, time(cc))
