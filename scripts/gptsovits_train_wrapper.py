"""Run upstream semantic training with an explicit first-update learning rate."""
import argparse
import os
from pathlib import Path
import sys
from functools import partial


def initialize_optimizer_lr(config, result):
    rate = float(config['optimizer']['lr_init'])
    if not 0 < rate <= .01:
        raise ValueError('Invalid initial learning rate')
    for group in result['optimizer'].param_groups:
        group['lr'] = rate
    return rate


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')
    parser = argparse.ArgumentParser()
    parser.add_argument('--config_file', required=True)
    args = parser.parse_args()
    root = Path(os.getenv('RM_GPTSOVITS_ROOT', Path.cwd())).resolve()
    if not (root / 'GPT_SoVITS/s1_train.py').is_file():
        raise SystemExit('Run from the GPT-SoVITS directory or set RM_GPTSOVITS_ROOT')
    sys.path[:0] = [str(root / 'GPT_SoVITS'), str(root)]
    import s1_train
    original = s1_train.Text2SemanticLightningModule.configure_optimizers

    def configured(module):
        result = original(module)
        rate = initialize_optimizer_lr(module.config, result)
        print('MeiMei actual initial optimizer learning rate:', rate, flush=True)
        return result

    s1_train.Text2SemanticLightningModule.configure_optimizers = configured
    # Rich's legacy Windows console can fail at the end of a successful hidden
    # run. Plain logs also keep background training reviewable.
    s1_train.Trainer = partial(s1_train.Trainer, enable_progress_bar=False)
    s1_train.main(args)


if __name__ == '__main__':
    main()
