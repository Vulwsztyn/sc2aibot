from multiprocessing import Process, Pipe
from pysc2.env import sc2_env, available_actions_printer


class SingleEnv:
    """
    This works like SubprocVecEnv but runs only one environment in the main process
    """
    def __init__(self, env):
        self.env = env
        self.n_envs = 1

    def step(self, actions):
        """
        :param actions: List[FunctionCall]
        :return:
        """
        assert len(actions) == 1  # only 1 environment
        action = actions[0]
        return [self.env.step([action])[0]]

    def reset_done_envs(self):
        pass

    def reset(self):
        return [self.env.reset()[0]]

    def close(self):
        self.env.close()


# below (worker, CloudpickleWrapper, SubprocVecEnv) copied from
# https://github.com/openai/baselines/blob/master/baselines/common/vec_env/subproc_vec_env.py
# with some sc2 specific modifications
def worker(remote, env_fn_wrapper):
    """
    Handling the:
    action -> [action] and  [timestep] -> timestep
    single-player conversions here
    """
    env = env_fn_wrapper.x()
    while True:
        cmd, action = remote.recv()
        if cmd == 'step':
            timesteps = env.step([action])
            assert len(timesteps) == 1
            remote.send(timesteps[0])
        elif cmd == 'reset':
            timesteps = env.reset()
            assert len(timesteps) == 1
            remote.send(timesteps[0])
        elif cmd == 'close':
            remote.close()
            break
        else:
            raise NotImplementedError


class CloudpickleWrapper(object):
    """
    Uses cloudpickle to serialize contents (otherwise multiprocessing tries to use pickle)
    """

    def __init__(self, x):
        self.x = x

    def __getstate__(self):
        import cloudpickle
        return cloudpickle.dumps(self.x)

    def __setstate__(self, ob):
        import pickle
        self.x = pickle.loads(ob)


class SubprocVecEnv:
    def __init__(self, env_fns):
        n_envs = len(env_fns)
        self.remotes, self.work_remotes = zip(*[Pipe() for _ in range(n_envs)])
        self.ps = [Process(target=worker, args=(work_remote, CloudpickleWrapper(env_fn)))
            for (work_remote, env_fn) in zip(self.work_remotes, env_fns)]
        for p in self.ps:
            p.start()

        self.n_envs = n_envs

    def _step_or_reset(self, command, actions=None):
        print('_step_or_reset')
        actions = actions or [None] * self.n_envs
        print('actions', actions)
        for remote, action in zip(self.remotes, actions):
            print((command, action))
            remote.send((command, action))
        timesteps = [remote.recv() for remote in self.remotes]
        print('timesteps', timesteps)
        return timesteps

    def step(self, actions):
        return self._step_or_reset("step", actions)

    def reset(self):
        return self._step_or_reset("reset", None)

    def close(self):
        for remote in self.remotes:
            remote.send(('close', None))
        for p in self.ps:
            p.join()

    def reset_done_envs(self):
        pass


def make_sc2env(**kwargs):
    env = sc2_env.SC2Env(**kwargs)
    # env = available_actions_printer.AvailableActionsPrinter(env)
    return env


