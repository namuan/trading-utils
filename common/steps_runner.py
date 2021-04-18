import logging
from time import sleep


def run(procedure, args):
    wait_period = args.wait_in_minutes
    run_once = args.run_once
    while True:
        context = {"args": args}
        for step in procedure:
            step_name = step.__class__.__name__
            try:
                logging.info(f"==> Running step: {step_name}")
                logging.debug(context)
                step.run(context)
            except Exception:
                logging.exception(f"Failure in step {step_name}")

        if run_once:
            break

        logging.info(f"😴 Sleeping for {wait_period} minutes")
        sleep(60 * wait_period)
