""" i/o utilities """


def get_edgelist(f_edgelist, delimiter=','):
    """
        This function returns an edgelist list from a file.

        Parameters
        ----------
        f_edgelist : str
            The path to the edgelist file

        delimiter : str
            The delimiter in the file

        Returns
        -------
        edgelist : list
            The list of tupled edges.

    """
    edgelist = []
    with open(f_edgelist, "r") as f:
        for line in f:
            line = line.replace('\r', '').replace('\n', '')  # remove all line breaks!
            edge = line.split(delimiter)
            # edgelist.append((str(int(edge[0]) - 1), str(int(edge[1]) - 1)))
            edgelist.append((str(int(edge[0])), str(int(edge[1]))))
    f.close()
    return edgelist

def get_types(f_types):
    """
        This function returns an edgelist list from a file.

        Parameters
        ----------
        f_edgelist : str
            The path to the types file

        Returns
        -------
        edgelist : list
            The list of types of each node.

        >>> import ioutils
        >>> edgelist = get_types(f_types)
        >>> print(edgelist)

    """
    types = []
    with open(f_types, "r") as f:
        for line in f:
            types.append(str(int(line.replace('\n', ""))))
    f.close()
    return types


def save_mb_to_file(path, mb):
    """Save the group membership list to a file path.

    Parameters
    ----------
    path : str, required
        File path for the list to save to.

    mb : list[int], required
        Group membership list.
    """
    assert type(mb) is list, "[ERROR] the type of the second input parameter should be a list"
    num_nodes = len(mb)
    with open(path, "w") as f:
        for i in range(0, num_nodes):
            f.write(str(mb[i]) + "\n")
