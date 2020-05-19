class DefaultOrder:
    def __init__(self, order):
        self.order_map = {}
        for idx, elem in enumerate(order):
            self.order_map[elem] = idx
    def __call__(self, elem):
        if elem not in self.order_map:
            self.order_map[elem] = len(self.order_map)
        return self.order_map[elem]

def find_metric_name(automl):
    try:
        statistics = automl.sprint_statistics()
        lines = statistics.split("\n")
        my_line = list(filter(lambda x: x.upper().find("METRIC") > -1, lines))[0]
        metric = my_line.split(":")[1].strip().upper()
        return metric
    except Exception as e:
        return "METRIC"

def import_autosklearn(automl, source='auto-sklearn'):
    cv_results = automl.cv_results_
    node_order = DefaultOrder(['data_preprocessing', 'feature_preprocessor','classifier', 'regressor'])
    n_models = len(cv_results['mean_test_score'])
    pipelines = [];
    metric_name = find_metric_name(automl)
    for i in range(n_models):
        # Computing auxiliary pipeline structure
        struct = {}
        for key in cv_results['params'][i]:
            split = key.split(":")
            if split[1] == '__choice__' or split[1] == 'strategy':
                continue
            module_type = split[0]
            if module_type not in struct:
                struct[module_type] = {}    
            module_name = split[1]
            if module_name not in struct[module_type]:
                struct[module_type][module_name] = {}
            module_param = '_'.join(filter(lambda x: x != '__choice__', split[2:]))
            struct[module_type][module_name][module_param] = cv_results['params'][i][key]
        ordered_types = struct.keys()
        ordered_types = sorted(ordered_types, key=lambda x: node_order(x))

        # Creating pipeline graph
        pipeline = {
            'inputs': [{'name': 'input dataset'}],
            'steps': [],
            'scores': [{
                'metric': {'metric': metric_name, 'params': {'pos_label': '1'}},
                'normalized': cv_results['mean_test_score'][i],
                'value': cv_results['mean_test_score'][i],
            }],
            'pipeline_source': {'name': source},
            'pipeline_digest': '{}'.format(i),
            'time': cv_results['mean_fit_time'][i],
        }
        prev_list = ['inputs.0']
        cur_step_idx = 0
        for module_type in ordered_types:
            new_prev_list = []
            modules = struct[module_type]
            for module in modules:
                step_ref = 'steps.{}.produce'.format(cur_step_idx)
                cur_step_idx += 1
                new_prev_list.append(step_ref)
                step = {
                    'primitive': {'python_path':'auto_sklearn.primitives.{}.{}'.format(module_type, module), 'name': module},
                    'arguments':{},
                    'outputs': [{'id': 'produce'}],
                    'reference': {'type': 'CONTAINER', 'data': step_ref},
                    'hyperparams': {}
                }
                for param in struct[module_type][module]:
                    step['hyperparams'][param] = {
                        'type': 'VALUE',
                        'data': struct[module_type][module][param]
                    }                
                for idx, prev in enumerate(prev_list):
                    cur_argument_idx = 'input{}'.format(idx)
                    step['arguments'][cur_argument_idx] = {
                        'data': prev
                    }
                pipeline['steps'].append(step)
            prev_list = new_prev_list
        pipeline['outputs'] = []
        for prev in prev_list:
            pipeline['outputs'].append({'data': prev})        
        pipelines.append(pipeline)
    return pipelines